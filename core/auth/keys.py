"""Deployment key material.

Every value is read inside a function: reading settings at import time is what
makes a module impossible to reconfigure in tests and in a worker process.

Provisioning the keypair, deriving its `kid` and publishing a JWKS document
belong to the ticket that switches encoding over; this module only resolves what
a deployment has already been given.
"""

import jwt
from django.conf import settings
from graphql_jwt.settings import jwt_settings

PER_USER = "per_user"
DEPLOYMENT = "deployment"


def mode():
    """`per_user` (the default) or `deployment`.

    Only encoding consults this. Decoding accepts both shapes for the whole
    migration window - a mode-gated decode would invalidate every outstanding
    token the moment a deployment flipped the switch.
    """
    return getattr(settings, "JWT_KEY_MODE", PER_USER)


def deployment_keys():
    """`{kid: verification key}`. Empty until a deployment provisions one."""
    return getattr(settings, "JWT_DEPLOYMENT_KEYS", None) or {}


def active_kid():
    """The `kid` encoding will stamp once it moves to the deployment key."""
    return getattr(settings, "JWT_ACTIVE_KID", None)


def algorithm():
    """One algorithm, deliberately.

    Accepting a list next to a set of public keys is what makes algorithm
    confusion possible - an attacker signs HS256 with a key everyone can read.
    """
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
