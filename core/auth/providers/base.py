import abc
from typing import Mapping

from core.auth.identity import IdentityClaims, IdentitySpec


class IdentityProvider(abc.ABC):
    """Three methods are the whole contract. `verify` does no database access,
    which is why the legacy per-user-key path is a provider of its own.
    """

    id: str

    #: "never" = the user must already exist; "first_login" = provision once,
    #: never update roles afterwards.
    provision: str = "never"

    @abc.abstractmethod
    def accepts(self, header: Mapping, unverified: Mapping) -> bool:
        """Routing only. Must not be trusted for anything else."""

    @abc.abstractmethod
    def verify(self, token: str) -> IdentityClaims:
        """Raise jwt.InvalidTokenError on any failure."""

    def to_identity(self, claims: IdentityClaims) -> IdentitySpec:
        return IdentitySpec(
            username=claims.username, subject=claims.subject, provider_id=self.id
        )
