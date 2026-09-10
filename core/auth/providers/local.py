import jwt
from graphql_jwt.settings import jwt_settings

from core.auth import keys
from core.auth.claims import claims_from_payload
from core.auth.providers.base import IdentityProvider


class LocalProvider(IdentityProvider):
    """openIMIS-issued tokens signed with the deployment keypair.

    Trusting the unverified `kid` is safe because it only picks from a fixed key
    set: a forged one selects a key that then fails verification. Contrast
    providers/legacy.py, where the key is chosen by an unverified *identity*.
    """

    id = "local"

    def accepts(self, header, unverified):
        if header.get("kid") is None:
            return False
        issuer = unverified.get("iss")
        return issuer is None or issuer == keys.issuer()

    def verify(self, token):
        kid = jwt.get_unverified_header(token).get("kid")
        payload = jwt.decode(
            token,
            keys.verification_key(kid),
            algorithms=[keys.algorithm()],
            audience=keys.audience(),
            issuer=keys.issuer(),
            leeway=jwt_settings.JWT_LEEWAY,
            options={
                "require": ["exp", "username"],
                "verify_exp": jwt_settings.JWT_VERIFY_EXPIRATION,
                "verify_aud": keys.audience() is not None,
                "verify_signature": jwt_settings.JWT_VERIFY,
            },
        )
        return claims_from_payload(payload)
