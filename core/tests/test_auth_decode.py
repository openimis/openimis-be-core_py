from calendar import timegm
from dataclasses import dataclass
from datetime import datetime, timedelta
from secrets import token_hex

import jwt as pyjwt
from django.test import TestCase, override_settings
from graphql_jwt.settings import jwt_settings
from graphql_jwt.shortcuts import get_token

from core.auth import decode
from core.models import InteractiveUser, TechnicalUser, User
from core.test_helpers import create_test_interactive_user

DEPLOYMENT_KID = "deployment-2026-09"
DEPLOYMENT_KEY = token_hex(32)

with_deployment_key = override_settings(
    JWT_DEPLOYMENT_KEYS={DEPLOYMENT_KID: DEPLOYMENT_KEY},
    JWT_DEPLOYMENT_ALGORITHM="HS256",
)


@dataclass
class DummyContext:
    """graphql_jwt hands the encode handler a context; only .user is read."""

    user: User


def _password():
    """Generated, so no password-shaped literal ends up in the repository."""
    return token_hex(16) + "Aa1!"


def _exp(days=1):
    return timegm((datetime.utcnow() + timedelta(days=days)).utctimetuple())


def _sign(key, kid=None, algorithm="HS256", **claims):
    payload = {"exp": _exp(), **claims}
    return pyjwt.encode(
        payload, key, algorithm=algorithm, headers={"kid": kid} if kid else None
    )


class LegacyTokenDecodeTest(TestCase):
    """Tokens signed with the per-user password salt - every token in
    circulation on every deployment today. They carry no kid.
    """

    def setUp(self):
        self.password = _password()
        self.user = create_test_interactive_user(
            username="authLegacy", password=self.password
        )
        self.token = get_token(self.user, DummyContext(user=self.user))

    def test_legacy_token_decodes(self):
        self.assertEqual(decode(self.token)["username"], self.user.username)

    def test_legacy_token_is_verified_against_the_user_salt(self):
        # Rotating the salt must still invalidate the token: that side effect is
        # what revocation relies on until the not-before check replaces it.
        self.user.i_user.set_password(self.password)
        self.user.i_user.save()

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(self.token)

    def test_technical_user_token_decodes(self):
        # A technical user has no InteractiveUser row and so no salt; its token
        # is signed with the deployment-wide secret. Issuing one still raises
        # upstream - that is fixed when the legacy path goes away, not here.
        TechnicalUser(username="authTech", email="authTech@example.test").save()
        token = _sign(jwt_settings.JWT_SECRET_KEY, username="authTech")

        self.assertEqual(decode(token)["username"], "authTech")

    def test_user_without_a_salt_is_verified_with_the_deployment_wide_secret(self):
        # A user created without a password keeps private_key NULL, so their
        # token is signed with the global secret while password users get a
        # per-user one. Both regimes already exist; the key split unifies them.
        user = create_test_interactive_user(username="authNoSalt", password=_password())
        InteractiveUser.objects.filter(pk=user.i_user.pk).update(private_key=None)
        token = _sign(jwt_settings.JWT_SECRET_KEY, username="authNoSalt")

        self.assertEqual(decode(token)["username"], "authNoSalt")

    def test_unsigned_token_is_rejected(self):
        token = _sign(token_hex(32), username="authLegacy")

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)


@with_deployment_key
class DeploymentKeyDecodeTest(TestCase):
    """Tokens signed with the deployment keypair, selected by the kid header.

    Every assertion here is also an assertion about the error type: only
    InvalidTokenError, DecodeError and ExpiredSignatureError are translated by
    graphql_jwt.utils.get_payload, so any other exception type reaches the
    client as a 500 instead of an authentication failure.
    """

    def test_deployment_token_decodes_without_touching_the_database(self):
        token = _sign(DEPLOYMENT_KEY, kid=DEPLOYMENT_KID, username="noSuchUser")

        with self.assertNumQueries(0):
            payload = decode(token)

        self.assertEqual(payload["username"], "noSuchUser")

    def test_unknown_kid_does_not_fall_back_to_the_legacy_path(self):
        token = _sign(DEPLOYMENT_KEY, kid="not-provisioned", username="noSuchUser")

        with self.assertNumQueries(0):
            with self.assertRaises(pyjwt.InvalidTokenError):
                decode(token)

    def test_kid_signed_with_the_wrong_key_is_rejected(self):
        token = _sign(token_hex(32), kid=DEPLOYMENT_KID, username="noSuchUser")

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)

    def test_expired_deployment_token_is_rejected(self):
        token = _sign(
            DEPLOYMENT_KEY, kid=DEPLOYMENT_KID, username="noSuchUser", exp=_exp(days=-1)
        )

        with self.assertRaises(pyjwt.ExpiredSignatureError):
            decode(token)

    def test_token_without_username_is_rejected(self):
        token = _sign(DEPLOYMENT_KEY, kid=DEPLOYMENT_KID, sub="noSuchUser")

        with self.assertRaises(pyjwt.MissingRequiredClaimError):
            decode(token)


class NoDeploymentKeyConfiguredTest(TestCase):
    """The default state: no keypair provisioned, so no kid resolves. A
    deployment upgrading without provisioning a key is unaffected.
    """

    def test_kid_token_is_rejected_when_no_key_is_provisioned(self):
        token = _sign(DEPLOYMENT_KEY, kid=DEPLOYMENT_KID, username="noSuchUser")

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)

    def test_legacy_tokens_still_work(self):
        password = _password()
        user = create_test_interactive_user(username="authNoKey", password=password)
        token = get_token(user, DummyContext(user=user))

        self.assertEqual(decode(token)["username"], user.username)
