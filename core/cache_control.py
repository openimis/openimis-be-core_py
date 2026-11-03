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
# Expiry and coherence
#
# Every entry expires: the overall CACHE_OBJECT_TTL applies whenever a caller
# gives no timeout, or None. An entry that lives forever outlives any
# invalidation it misses.
#
# A process-local backend (LocMemCache) is only coherent when every write
# happens in the process that reads: with async mutations the write, and the
# invalidation its signals trigger, run in the Celery worker, and never reach
# the web processes' copies - nor the other way round. Such a cache is then not
# used at all: values live in a memo for the current request or task only.
# ---------------------------------------------------------------------------

PROCESS_LOCAL_BACKENDS = ("LocMemCache", "DummyCache")


def default_ttl():
    return getattr(settings, "CACHE_OBJECT_TTL", 3600)


def _timeout(timeout):
    return default_ttl() if timeout is _UNSET or timeout is None else timeout


def _runs_out_of_process():
    import core

    return bool(getattr(core, "async_mutations", False))


def cache_is_coherent(alias="default"):
    """Whether entries of this cache alias can be trusted across requests."""
    if get_cache_info(alias)["backend_short"] not in PROCESS_LOCAL_BACKENDS:
        return True
    return not _runs_out_of_process()


def _memo():
    # request (or Celery task) scoped; cleared by core.utils.clear_access_cache
    from core.utils import get_cache_memo

    return get_cache_memo()


def cache_memo_forget(prefixes, alias="default"):
    """Drop the request memo's entries whose key starts with one of ``prefixes``.

    For invalidations that cannot name their keys (a whole key space), next to
    whatever the caller does on the backend itself.
    """
    prefixes = tuple(prefixes)
    memo = _memo()
    for entry in [entry for entry in memo if entry[0] == alias and str(entry[1]).startswith(prefixes)]:
        del memo[entry]


# ---------------------------------------------------------------------------
# Fault tolerant accessors, for the default cache or a named alias
# ---------------------------------------------------------------------------

def _cache_call(operation, default, *args, alias="default", **kwargs):
    try:
        backend = cache if alias == "default" else caches[alias]
        return getattr(backend, operation)(*args, **kwargs)
    except Exception as exc:
        # a failing cache must not propagate: the caller either has a database
        # fallback (reads) or has already written to the database (writes)
        logger.warning("cache %s failed on %s: %s", operation, args[:1], exc)
        return default


def cache_get(key, default=None, alias="default"):
    """``cache.get``, returning ``default`` when the backend is unavailable."""
    if not cache_is_coherent(alias):
        return _memo().get((alias, key), default)
    return _cache_call("get", default, key, default, alias=alias)


def cache_get_many(keys, alias="default"):
    """``cache.get_many``, returning ``{}`` when the backend is unavailable."""
    if not cache_is_coherent(alias):
        memo = _memo()
        return {key: memo[(alias, key)] for key in keys if (alias, key) in memo}
    return _cache_call("get_many", {}, keys, alias=alias)


def cache_set(key, value, timeout=_UNSET, alias="default"):
    """``cache.set``; returns False when the backend is unavailable."""
    if not cache_is_coherent(alias):
        _memo()[(alias, key)] = value
        return True
    return _cache_call("set", False, key, value, timeout=_timeout(timeout), alias=alias) is not False


def cache_set_many(mapping, timeout=_UNSET, alias="default"):
    """``cache.set_many``; returns False when the backend is unavailable."""
    if not mapping:
        return True
    if not cache_is_coherent(alias):
        _memo().update({(alias, key): value for key, value in mapping.items()})
        return True
    return _cache_call("set_many", False, mapping, timeout=_timeout(timeout), alias=alias) is not False


def cache_delete(key, alias="default"):
    """``cache.delete``; returns False when the backend is unavailable."""
    _memo().pop((alias, key), None)
    return _cache_call("delete", False, key, alias=alias) is not False


def cache_delete_many(keys, alias="default"):
    """``cache.delete_many``; returns False when the backend is unavailable."""
    keys = list(keys)
    if not keys:
        return True
    memo = _memo()
    for key in keys:
        memo.pop((alias, key), None)
    return _cache_call("delete_many", False, keys, alias=alias) is not False


# ---------------------------------------------------------------------------
# Rights / user flag key space
#
# InteractiveUser.rights is cached per user id, but the events that invalidate
# it happen on *other* models (Role, RoleRight, UserRole). The model cache
# (core.utils.CachedModelMixin, keyed by model and pk) therefore cannot own
# these entries: they are read, written and dropped through the helpers below.
# ---------------------------------------------------------------------------

RIGHTS_KEY = "rights_{}"
OFFICER_KEY = "user_eo_{}"
CLAIM_ADMIN_KEY = "user_ca_{}"


def get_user_rights(user_id):
    return cache_get(RIGHTS_KEY.format(user_id))


def set_user_rights(user_id, rights):
    return cache_set(RIGHTS_KEY.format(user_id), rights)


def invalidate_user_rights(user_id):
    """Drop the cached rights of one interactive user."""
    if user_id is None:
        return
    cache_delete_many([RIGHTS_KEY.format(user_id)])


def invalidate_users_rights(user_ids):
    """Drop the cached rights of several interactive users."""
    keys = [
        RIGHTS_KEY.format(user_id) for user_id in user_ids if user_id is not None
    ]
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
    return cache_set(OFFICER_KEY.format(login_name), is_officer)


def invalidate_officer(login_name):
    return cache_delete(OFFICER_KEY.format(login_name))


def get_claim_admin_flag(login_name):
    return cache_get(CLAIM_ADMIN_KEY.format(login_name))


def set_claim_admin_flag(login_name, is_claim_admin):
    return cache_set(CLAIM_ADMIN_KEY.format(login_name), is_claim_admin)


def invalidate_claim_admin(login_name):
    return cache_delete(CLAIM_ADMIN_KEY.format(login_name))
