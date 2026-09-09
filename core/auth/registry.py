import json
from functools import lru_cache

import jwt
from django.conf import settings
from django.utils.module_loading import import_string

from core.auth.providers.legacy import LegacyUserKeyProvider
from core.auth.providers.local import LocalProvider


def _registration():
    """`AUTH_TOKEN_PROVIDERS`: what a deployment adds to the built-in two.

    An entry is either a dotted path, or a mapping carrying one under
    `provider` whose remaining keys become constructor arguments. The second
    form is what a configured provider needs - an external identity provider is
    an issuer, an audience and a claim mapping, not a subclass - so the
    extension point does not have to change to accept one.
    """
    return getattr(settings, "AUTH_TOKEN_PROVIDERS", None) or ()


def _instantiate(entry):
    if isinstance(entry, str):
        return import_string(entry)()
    config = dict(entry)
    return import_string(config.pop("provider"))(**config)


@lru_cache(maxsize=8)
def _build(_fingerprint):
    """Built once per distinct registration.

    Keyed on a fingerprint of the setting rather than held in a module-level
    singleton, so an override takes effect instead of being defeated by a list
    built during the first request. Instances are reused rather than rebuilt per
    call because a configured provider will own a key-set client, and caching
    those keys is the point of it.
    """
    return (
        LocalProvider(),
        LegacyUserKeyProvider(),
        *(_instantiate(entry) for entry in _registration()),
    )


def providers():
    return _build(json.dumps(_registration(), sort_keys=True, default=str))


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
