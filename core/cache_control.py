"""
Single entry point for openIMIS cache access.

Two reasons for everything to go through here:

* a cache is an optimisation. A backend that is down (or simply not deployed
  for the one-off containers that run ``migrate`` / ``load_fixtures``) must
  degrade to a cache miss, never abort the database operation that triggered
  the read or the invalidation. The ``cache_*`` helpers below own that
  tolerance so no call site has to remember it.
* the key spaces are named once, here, instead of being spelled out with an
  f-string at each call site.
"""

import logging

from django.apps import apps
from django.conf import settings
from django.core.cache import cache, caches

logger = logging.getLogger(__name__)

_UNSET = object()


class UnknownCacheAliasError(ValueError):
    """Raised when a requested cache alias is not in settings.CACHES."""


def get_configured_cache_aliases():
    """Return cache aliases from settings, preserving configuration order."""
    aliases = list(getattr(settings, "CACHES", {}) or {})
    return aliases or ["default"]


def get_cache_info(alias):
    """Return display metadata for a configured cache alias."""
    conf = (getattr(settings, "CACHES", {}) or {}).get(alias, {})
    backend = conf.get("BACKEND") or caches[alias].__class__.__name__
    return {
        "alias": alias,
        "backend": backend,
        "backend_short": backend.rsplit(".", 1)[-1],
        "key_prefix": conf.get("KEY_PREFIX") or "",
        "location": conf.get("LOCATION") or "",
    }


def list_cache_info(aliases=None):
    """Return metadata for the given aliases, or all configured caches."""
    if aliases is None:
        aliases = get_configured_cache_aliases()
    return [get_cache_info(alias) for alias in aliases]


def resolve_cache_aliases(aliases=None):
    """
    Normalize the aliases to flush.

    ``None`` or an empty sequence means every configured cache. Unknown names
    raise ``UnknownCacheAliasError`` before any cache is touched.
    """
    available = get_configured_cache_aliases()
    if not aliases:
        return list(available)

    unknown = [alias for alias in aliases if alias not in available]
    if unknown:
        raise UnknownCacheAliasError(
            "Unknown cache alias(es): {}. Configured: {}".format(
                ", ".join(unknown),
                ", ".join(available),
            )
        )

    resolved = []
    seen = set()
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            resolved.append(alias)
    return resolved


def flush_caches(aliases=None):
    """
    Clear the given Django cache aliases, or all configured caches.

    Returns ``(flushed, errors)`` where ``flushed`` is a list of aliases that
    were cleared and ``errors`` is a list of ``(alias, message)`` tuples.
    """
    resolved = resolve_cache_aliases(aliases)
    flushed = []
    errors = []
    for alias in resolved:
        try:
            caches[alias].clear()
            flushed.append(alias)
        except Exception as exc:
            errors.append((alias, str(exc)))
    return flushed, errors


# ---------------------------------------------------------------------------
# Fault tolerant accessors for the default cache
# ---------------------------------------------------------------------------

def _cache_call(operation, default, *args, **kwargs):
    try:
        return getattr(cache, operation)(*args, **kwargs)
    except Exception as exc:
        # a failing cache must not propagate: the caller either has a database
        # fallback (reads) or has already written to the database (writes)
        logger.warning("cache %s failed on %s: %s", operation, args[:1], exc)
        return default


def cache_get(key, default=None):
    """``cache.get``, returning ``default`` when the backend is unavailable."""
    return _cache_call("get", default, key, default)


def cache_get_many(keys):
    """``cache.get_many``, returning ``{}`` when the backend is unavailable."""
    return _cache_call("get_many", {}, keys)


def cache_set(key, value, timeout=_UNSET):
    """``cache.set``; returns False when the backend is unavailable."""
    kwargs = {} if timeout is _UNSET else {"timeout": timeout}
    return _cache_call("set", False, key, value, **kwargs) is not False


def cache_set_many(mapping, timeout=_UNSET):
    """``cache.set_many``; returns False when the backend is unavailable."""
    if not mapping:
        return True
    kwargs = {} if timeout is _UNSET else {"timeout": timeout}
    return _cache_call("set_many", False, mapping, **kwargs) is not False


def cache_delete(key):
    """``cache.delete``; returns False when the backend is unavailable."""
    return _cache_call("delete", False, key) is not False


def cache_delete_many(keys):
    """``cache.delete_many``; returns False when the backend is unavailable."""
    keys = list(keys)
    if not keys:
        return True
    return _cache_call("delete_many", False, keys) is not False


# ---------------------------------------------------------------------------
# Rights / user flag key space
#
# InteractiveUser.rights and .is_imis_admin are cached per user id, but the
# events that invalidate them happen on *other* models (Role, RoleRight,
# UserRole). The model cache (core.utils.CachedModelMixin, keyed by model and
# pk) therefore cannot own these entries: they are read, written and dropped
# through the helpers below.
# ---------------------------------------------------------------------------

RIGHTS_KEY = "rights_{}"
IS_ADMIN_KEY = "is_admin_{}"
OFFICER_KEY = "user_eo_{}"
CLAIM_ADMIN_KEY = "user_ca_{}"

IS_ADMIN_TTL = 600


def get_user_rights(user_id):
    return cache_get(RIGHTS_KEY.format(user_id))


def set_user_rights(user_id, rights):
    return cache_set(RIGHTS_KEY.format(user_id), rights, timeout=None)


def get_user_is_admin(user_id):
    return cache_get(IS_ADMIN_KEY.format(user_id))


def set_user_is_admin(user_id, is_admin):
    return cache_set(IS_ADMIN_KEY.format(user_id), is_admin, timeout=IS_ADMIN_TTL)


def invalidate_user_rights(user_id):
    """Drop the cached rights and admin flag of one interactive user."""
    if user_id is None:
        return
    cache_delete_many(
        [RIGHTS_KEY.format(user_id), IS_ADMIN_KEY.format(user_id)]
    )


def invalidate_users_rights(user_ids):
    """Drop the cached rights and admin flag of several interactive users."""
    keys = []
    for user_id in user_ids:
        if user_id is None:
            continue
        keys.append(RIGHTS_KEY.format(user_id))
        keys.append(IS_ADMIN_KEY.format(user_id))
    cache_delete_many(keys)


def invalidate_role_rights(role_id):
    """
    Drop the cached rights of every user holding this role.

    A role level change cannot target a single key. Resolving the members costs
    one query, on writes that are rare; the alternative used to be
    ``cache.delete_pattern`` when the backend offers it and ``cache.clear()``
    otherwise - and ``django.core.cache.backends.redis`` has no
    ``delete_pattern``, so a single role rename used to FLUSHDB the whole redis
    instance, every other openIMIS cache alias included.

    Membership is read without a validity filter: dropping the key of a user
    whose role assignment has expired is harmless, keeping a stale one is not.
    """
    if role_id is None:
        return
    user_role = apps.get_model("core", "UserRole")
    invalidate_users_rights(
        set(user_role.objects.filter(role_id=role_id).values_list("user_id", flat=True))
    )


def get_officer_flag(login_name):
    return cache_get(OFFICER_KEY.format(login_name))


def set_officer_flag(login_name, is_officer):
    return cache_set(OFFICER_KEY.format(login_name), is_officer, timeout=None)


def invalidate_officer(login_name):
    return cache_delete(OFFICER_KEY.format(login_name))


def get_claim_admin_flag(login_name):
    return cache_get(CLAIM_ADMIN_KEY.format(login_name))


def set_claim_admin_flag(login_name, is_claim_admin):
    return cache_set(CLAIM_ADMIN_KEY.format(login_name), is_claim_admin, timeout=None)


def invalidate_claim_admin(login_name):
    return cache_delete(CLAIM_ADMIN_KEY.format(login_name))
