import json
from functools import lru_cache

import jwt
from django.conf import settings
from django.utils.module_loading import import_string

from core.auth.providers.legacy import LegacyUserKeyProvider
from core.auth.providers.local import LocalProvider


def _registration():
    """`AUTH_TOKEN_PROVIDERS`: providers a deployment adds to the built-in two.

    An entry is a dotted path, or a mapping carrying one under `provider` whose
    remaining keys become constructor arguments.
    """
    return getattr(settings, "AUTH_TOKEN_PROVIDERS", None) or ()


def _instantiate(entry):
    if isinstance(entry, str):
        return import_string(entry)()
    config = dict(entry)
    return import_string(config.pop("provider"))(**config)


@lru_cache(maxsize=8)
def _build(_fingerprint):
    # Keyed on a fingerprint of the setting rather than a module-level
    # singleton, so an override is not defeated by a list built on first use.
    return (
        LocalProvider(),
        LegacyUserKeyProvider(),
        *(_instantiate(entry) for entry in _registration()),
    )


def providers():
    return _build(json.dumps(_registration(), sort_keys=True, default=str))


def resolve(token):
    """Which provider owns this token. Routing only - nothing here is verified."""
    header = jwt.get_unverified_header(token)
    unverified = jwt.decode(token, options={"verify_signature": False})
    for provider in providers():
        if provider.accepts(header, unverified):
            return provider
    raise jwt.InvalidIssuerError(unverified.get("iss"))
