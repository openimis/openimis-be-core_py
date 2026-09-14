"""Startup checks for the deployment key material.

The first system checks in core. They exist because both failures are otherwise
invisible until something depends on them: an unprovisioned deployment signs
nothing and only finds out at the first login, and an unpublishable verification
key is dropped silently by the JWKS view on every request.
"""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

from core.auth import keys


@register(Tags.security)
def signing_key_is_provisioned(app_configs, **kwargs):
    try:
        provisioned = keys.signing_key()
    except ValueError as exc:
        # keys.signing_key raises for material that will not load, and Django
        # does not catch exceptions from checks - reported, not a traceback.
        return [Error(str(exc), id="core.auth.E001")]
    if provisioned is None:
        return [
            Error(
                "JWT_SIGNING_KEY is not set. openIMIS signs tokens only with the "
                "provisioned deployment keypair; see OP-3132.",
                id="core.auth.E001",
            )
        ]
    return []


@register(Tags.security)
def deployment_keys_are_publishable(app_configs, **kwargs):
    configured = getattr(settings, "JWT_DEPLOYMENT_KEYS", None) or {}
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
