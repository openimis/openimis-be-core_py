from dataclasses import dataclass
from typing import Any, Mapping, Optional

import jwt


@dataclass(frozen=True)
class Claims:
    """What a verified token said. Providers return this; nothing else."""

    raw: Mapping[str, Any]
    issuer: str
    subject: str
    username: str
    expires_at: int
    issued_at: Optional[int] = None


@dataclass(frozen=True)
class IdentitySpec:
    """What a provider knows about a person. Consumed only by provisioning."""

    username: str
    subject: str
    email: Optional[str] = None
    last_name: Optional[str] = None
    other_names: Optional[str] = None
    roles: tuple = ()
    provider_id: str = "local"


def issued_at_from(payload):
    """openIMIS tokens carry no `iat`.

    graphql_jwt writes `origIat` only when refresh is enabled, and core's
    encoder writes `nbf`; neither writes `iat`. Once encoding moves to the
    deployment key it will emit a real one, and this fallback will only serve
    tokens issued inside the migration window.
    """
    for claim in ("iat", "origIat", "nbf"):
        value = payload.get(claim)
        if value is not None:
            return value
    return None


def claims_from_payload(payload):
    """Build Claims from an openIMIS-issued payload.

    A missing username has to surface as an InvalidTokenError, not a KeyError:
    graphql_jwt.utils.get_payload translates only InvalidTokenError, DecodeError
    and ExpiredSignatureError, so anything else reaches the client as a 500.
    """
    for claim in ("username", "exp"):
        if not payload.get(claim):
            raise jwt.MissingRequiredClaimError(claim)
    return Claims(
        raw=payload,
        issuer=payload.get("iss") or "",
        subject=payload["username"],
        username=payload["username"],
        expires_at=payload["exp"],
        issued_at=issued_at_from(payload),
    )
