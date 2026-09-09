from functools import lru_cache

import jwt
from django.conf import settings
from django.utils.module_loading import import_string

from core.auth.providers.legacy import LegacyUserKeyProvider
from core.auth.providers.local import LocalProvider


@lru_cache(maxsize=8)
def _build(registration):
    """Built once per distinct registration.

    The cache key is the registration itself rather than a module-level
    singleton, so a settings override takes effect instead of being defeated by
    a list built during the first request.
    """
    return (
        LocalProvider(),
        LegacyUserKeyProvider(),
        *(import_string(path)() for path in registration),
    )


def providers():
    return _build(tuple(getattr(settings, "AUTH_TOKEN_PROVIDERS", None) or ()))


def resolve(token):
    """Which provider owns this token. Routing only - nothing here is verified.

    Order matters: `kid` present is a deployment-key token, `kid` absent is a
    legacy one, and an issuer belonging to neither is rejected rather than
    quietly handed to the local path.
    """
    header = jwt.get_unverified_header(token)
    unverified = jwt.decode(token, options={"verify_signature": False})
    for provider in providers():
        if provider.accepts(header, unverified):
            return provider
    raise jwt.InvalidIssuerError(unverified.get("iss"))
