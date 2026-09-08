from django.conf import settings
from django.core.cache import caches


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
