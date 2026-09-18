import jwt
from django.apps import apps
from graphql_jwt.settings import jwt_settings

from core.auth import keys
from core.auth.claims import claims_from_payload
from core.auth.providers.base import IdentityProvider


class LegacyUserKeyProvider(IdentityProvider):
    """Tokens signed with `InteractiveUser.private_key` - the password salt.

    The key can only be resolved from the unverified payload's username, so this
    is the one provider that queries the database before verifying. Decode
    options are unchanged, so tokens already in circulation verify as they do
    today. Deleting this file closes the migration window.
    """

    id = "legacy"

    def accepts(self, header, unverified):
        if header.get("kid") is not None:
            return False
        issuer = unverified.get("iss")
        return issuer is None or issuer == keys.issuer()

    def verify(self, token):
        unverified = jwt.decode(token, options={"verify_signature": False})
        payload = jwt.decode(
            token,
            self._key_for(unverified.get("username")),
            algorithms=[jwt_settings.JWT_ALGORITHM],
            audience=keys.audience(),
            issuer=keys.issuer(),
            leeway=jwt_settings.JWT_LEEWAY,
            options={
                "verify_exp": jwt_settings.JWT_VERIFY_EXPIRATION,
                "verify_aud": keys.audience() is not None,
                "verify_signature": jwt_settings.JWT_VERIFY,
            },
        )
        return claims_from_payload(payload)

    @staticmethod
    def _key_for(username):
        if not username:
            return _deployment_wide_key()
        # No .only()/.values_list(): both clone the queryset and drop the cache
        # CachedManager.filter() populates for a username lookup. The full
        # instance also avoids the deferred-field recursion in User.__getattr__.
        user_class = apps.get_model("core", "User")
        db_user = user_class.objects.filter(
            username=username, *user_class.filter_validity()
        ).first()
        if db_user and db_user.i_user and db_user.i_user.private_key:
            return db_user.i_user.private_key
        return _deployment_wide_key()


def _deployment_wide_key():
    # A user created without a password keeps private_key NULL and is already
    # signed with the global secret: two signing regimes coexist today.
    return getattr(jwt_settings, "JWT_PUBLIC_KEY", None) or jwt_settings.JWT_SECRET_KEY
