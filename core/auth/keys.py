"""Deployment key material. Read inside functions, never at import time."""

import jwt
from django.conf import settings
from graphql_jwt.settings import jwt_settings


def deployment_keys():
    """`{kid: verification key}`. Empty until a deployment provisions one."""
    return getattr(settings, "JWT_DEPLOYMENT_KEYS", None) or {}


def algorithm():
    # One algorithm, not a list: accepting several alongside public keys is what
    # makes algorithm confusion possible.
    return getattr(settings, "JWT_DEPLOYMENT_ALGORITHM", "RS256")


def verification_key(kid):
    keys = deployment_keys()
    if kid not in keys:
        raise jwt.InvalidTokenError(f"no deployment key for kid {kid!r}")
    return keys[kid]


def issuer():
    return jwt_settings.JWT_ISSUER


def audience():
    return jwt_settings.JWT_AUDIENCE
