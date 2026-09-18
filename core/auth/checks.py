"""Startup checks for what the auth layer needs a deployment to have provided.

Each is here because its failure is otherwise invisible until something depends
on it: an unprovisioned deployment signs nothing and only finds out at the first
login, an unpublishable verification key is dropped silently by the JWKS view on
every request, and a second-factor app left out of INSTALLED_APPS has no device
tables until an enrolment tries to write one.
"""

from collections.abc import Mapping

from django.apps import apps as django_apps
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


#: The apps that carry the device tables. core depends on the django-otp
#: distribution, but only the assembly can install its apps, so a core upgrade
#: without the matching assembly change is invisible until the first enrolment
#: raises ProgrammingError on a table that was never created.
SECOND_FACTOR_APPS = (
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
)


@register(Tags.security)
def second_factor_apps_are_installed(app_configs, **kwargs):
    missing = [
        app for app in SECOND_FACTOR_APPS if not django_apps.is_installed(app)
    ]
    if not missing:
        return []
    return [
        Error(
            "core.auth.second_factor verifies against django-otp device models, "
            f"but {', '.join(missing)} is missing from INSTALLED_APPS. The tables "
            "those models need are never created, so no second factor can be "
            "enrolled or verified.",
            id="core.auth.E004",
        )
    ]
