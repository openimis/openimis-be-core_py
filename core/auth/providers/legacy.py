import jwt
from django.apps import apps
from graphql_jwt.settings import jwt_settings

from core.auth import keys
from core.auth.claims import claims_from_payload
from core.auth.providers.base import IdentityProvider


class LegacyUserKeyProvider(IdentityProvider):
    """Tokens signed with `InteractiveUser.private_key` - the password salt.

    Resolving the key needs the identity, and the identity is only in the
    unverified payload, so this provider queries the database before it can
    verify anything. That is why it is not part of LocalProvider, whose
    `verify` is database-free, and why deleting one file closes the migration
    window once no token of this shape can still be valid.

    The decode options are today's, unchanged: acceptance criterion one is that
    existing tokens verify exactly as they do now.
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
        # Neither .only() nor .values_list() here. Both clone the queryset and
        # drop the result cache CachedManager.filter() populates for a username
        # lookup (`UNIQUE_FIELDS`, `CACHED_FK = {"i_user"}`), forcing a round
        # trip on every authenticated request. Taking the whole instance also
        # avoids the deferred-field recursion in User.__getattr__ -> _u, which
        # is what .only("i_user__private_key") used to hit for any user whose
        # i_user is NULL.
        user_class = apps.get_model("core", "User")
        db_user = user_class.objects.filter(
            username=username, *user_class.filter_validity()
        ).first()
        if db_user and db_user.i_user and db_user.i_user.private_key:
            return db_user.i_user.private_key
        return _deployment_wide_key()


def _deployment_wide_key():
    """What a user without a salt is already signed with.

    A user created without a password keeps `private_key` NULL, so federated
    users are signed with the global secret while password users get a per-user
    one: two signing regimes coexist today. The key split unifies them.
    """
    return getattr(jwt_settings, "JWT_PUBLIC_KEY", None) or jwt_settings.JWT_SECRET_KEY
