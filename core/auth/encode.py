"""Issuing tokens with the deployment keypair."""

import uuid
from calendar import timegm
from datetime import datetime

import jwt

from core.auth import keys


def encode(payload, context=None):
    """Sign with the deployment private key, naming it in the `kid` header.

    The algorithm comes from `keys.algorithm()`, not from
    `jwt_settings.JWT_ALGORITHM`, which the assembly sets to RS256 from a dead
    branch that still hands over the per-user salt as the key.
    """
    provisioned = keys.signing_key()
    if provisioned is None:
        raise ValueError(
            f"JWT_KEY_MODE is {keys.DEPLOYMENT!r} but JWT_SIGNING_KEY is not set"
        )
    private_key, kid = provisioned

    now = timegm(datetime.utcnow().utctimetuple())
    payload["jti"] = str(uuid.uuid4())
    payload["nbf"] = now
    payload["iat"] = now

    return jwt.encode(
        payload, private_key, algorithm=keys.algorithm(), headers={"kid": kid}
    )
