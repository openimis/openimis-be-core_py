import abc
from typing import Mapping

from core.auth.claims import Claims, IdentitySpec


class IdentityProvider(abc.ABC):
    """Three methods are the whole contract.

    `verify` is database-free for every provider but the legacy one, which is
    why that one is separate: it is what keeps an external identity provider off
    the request hot loop, and the dashboards authorization check a single rights
    lookup.
    """

    id: str

    #: "never" = the user must already exist; "first_login" = provision once,
    #: never update roles afterwards.
    provision: str = "never"

    @abc.abstractmethod
    def accepts(self, header: Mapping, unverified: Mapping) -> bool:
        """Routing only. Must not be trusted for anything else."""

    @abc.abstractmethod
    def verify(self, token: str) -> Claims:
        """Raise jwt.InvalidTokenError on any failure."""

    def to_identity(self, claims: Claims) -> IdentitySpec:
        return IdentitySpec(
            username=claims.username, subject=claims.subject, provider_id=self.id
        )
