"""Startup checks for the deployment key material.

The first system checks in core. They exist because both failures are otherwise
invisible until something depends on them: an unprovisioned deployment signs
nothing and only finds out at the first login, and an unpublishable verification
key is dropped silently by the JWKS view on every request.
"""

from collections.abc import Mapping

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

from core.auth import keys


@register(Tags.security)
def signing_key_is_provisioned(app_configs, **kwargs):
    try:
        provisioned = keys.signing_key()
    except (ValueError, TypeError) as exc:
        # Material that will not load: ValueError for an unreadable path or a
        # PEM that will not parse, TypeError for something that is not even a
        # string. Django does not catch exceptions from checks, so without this
        # the operator gets the traceback these checks exist to replace. Its own
        # id, so silencing "not provisioned" cannot also silence "will not load".
        return [Error(f"JWT_SIGNING_KEY cannot be loaded: {exc}", id="core.auth.E002")]
    if provisioned is None:
        return [
            Error(
                "JWT_SIGNING_KEY is not set. openIMIS signs tokens only with "
                "the deployment keypair, so one has to be provisioned and this "
                "setting pointed at it - an RSA private key, inline or as a path.",
                id="core.auth.E001",
            )
        ]
    return []


@register(Tags.security)
def deployment_keys_are_publishable(app_configs, **kwargs):
    configured = getattr(settings, "JWT_DEPLOYMENT_KEYS", None) or {}
    if not isinstance(configured, Mapping):
        return [
            Error(
                "JWT_DEPLOYMENT_KEYS must be a mapping of key id to verification "
                f"key, not {type(configured).__name__}.",
                id="core.auth.E003",
            )
        ]
    return [
        Warning(
            f"JWT_DEPLOYMENT_KEYS entry {kid!r} is not an RSA verification key. "
            "It cannot be published at the JWKS endpoint, so consumers reading "
            "that document will not verify tokens signed with it.",
            id="core.auth.W001",
        )
        for kid, key in configured.items()
        if keys.public_verification_key(key) is None
    ]


#: What an RSA key can sign with. JWT_SIGNING_KEY is always one (E001, E002).
_RSA_ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512")


@register(Tags.security)
def deployment_algorithm_fits_the_signing_key(app_configs, **kwargs):
    algorithm = keys.algorithm()
    if algorithm in _RSA_ALGORITHMS:
        return []
    return [
        Error(
            f"JWT_DEPLOYMENT_ALGORITHM is {algorithm!r}, which cannot sign with the "
            "RSA key in JWT_SIGNING_KEY, so every login would fail. Use one of "
            f"{', '.join(_RSA_ALGORITHMS)}, or leave it unset for RS256.",
            id="core.auth.E006",
        )
    ]
