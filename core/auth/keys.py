"""Deployment key material. Read inside functions, never at import time."""

import base64
import hashlib
import json
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from graphql_jwt.settings import jwt_settings
from jwt.algorithms import RSAAlgorithm

PER_USER = "per_user"
DEPLOYMENT = "deployment"


def mode():
    """Read by the encoder only - gating decode on it would log everyone out
    the moment a deployment flipped the switch.
    """
    return getattr(settings, "JWT_KEY_MODE", PER_USER)


def derive_kid(public_key):
    """RFC 7638 JWK thumbprint: a pure function of the key, so replicas agree
    without sharing anything.

    `to_jwk` also emits `key_ops`, which the thumbprint is not defined over.
    """
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    members = {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]}
    digest = hashlib.sha256(
        json.dumps(members, separators=(",", ":"), sort_keys=True).encode()
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@lru_cache(maxsize=4)
def _load(material):
    """Keyed on the material itself, so an override is a new key rather than a
    stale hit. Replacing a mounted file's contents in place therefore needs a
    restart, which is also true of every other setting here.
    """
    if "-----BEGIN" in material:
        pem = material.encode()
    else:
        try:
            with open(material, "rb") as handle:
                pem = handle.read()
        except OSError as exc:
            raise ValueError(
                f"JWT_SIGNING_KEY names a file that cannot be read: {exc}"
            ) from exc

    try:
        private_key = serialization.load_pem_private_key(pem, password=None)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"JWT_SIGNING_KEY is not a readable PEM private key: {exc}")

    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError(
            "JWT_SIGNING_KEY must be an RSA private key, got "
            f"{type(private_key).__name__}"
        )

    return private_key, derive_kid(private_key.public_key())


def signing_key():
    """`(private key, kid)`, or None when nothing is provisioned. The setting
    takes an inline PEM or a path to a mounted one.
    """
    material = getattr(settings, "JWT_SIGNING_KEY", None)
    if not material:
        return None
    return _load(material)


def deployment_keys():
    """`{kid: verification key}`. Empty until a deployment provisions one.

    The provisioned public half is here whatever the mode is: a token issued in
    deployment mode has to keep verifying if the mode is turned back off.
    `JWT_DEPLOYMENT_KEYS` merges over the top, which is what keeps a retired
    public key verifiable through a rotation.
    """
    configured = getattr(settings, "JWT_DEPLOYMENT_KEYS", None) or {}
    provisioned = signing_key()
    if provisioned is None:
        return dict(configured)
    private_key, kid = provisioned
    return {kid: private_key.public_key(), **configured}


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
