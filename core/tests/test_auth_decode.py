from calendar import timegm
from dataclasses import dataclass
from datetime import datetime, timedelta
from secrets import token_hex

import jwt as pyjwt
from django.test import TestCase, override_settings
from graphql_jwt.settings import jwt_settings
from graphql_jwt.shortcuts import get_token

from core.auth import decode
from core.models import InteractiveUser, User
from core.test_helpers import (
    create_test_interactive_user,
    create_test_technical_user,
)

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
    # iat by default: the encoder always emits one, so a fixture without it is
    # testing a token shape that no longer exists. Pass iat=None for that case.
    payload = {"exp": _exp(), "iat": _exp(days=0), **claims}
    payload = {k: v for k, v in payload.items() if v is not None}
    return pyjwt.encode(
        payload, key, algorithm=algorithm, headers={"kid": kid} if kid else None
    )


class LegacyTokenDecodeTest(TestCase):
    """Tokens signed with the per-user salt - what every deployment issues
    today. They carry no kid.
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
        # Rotating the salt is what revocation relies on until the not-before
        # check replaces it.
        self.user.i_user.set_password(self.password)
        self.user.i_user.save()

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(self.token)

    def test_technical_user_token_decodes(self):
        # No InteractiveUser row means no salt, so the deployment-wide secret
        # signs it. Issuing one still raises upstream; not fixed here.
        create_test_technical_user(username="authTech")
        token = _sign(jwt_settings.JWT_SECRET_KEY, username="authTech")

        self.assertEqual(decode(token)["username"], "authTech")

    def test_user_without_a_salt_is_verified_with_the_deployment_wide_secret(self):
        # private_key NULL means the global secret signs it - the second of the
        # two regimes that already coexist.
        user = create_test_interactive_user(username="authNoSalt", password=_password())
        InteractiveUser.objects.filter(pk=user.i_user.pk).update(private_key=None)
        # iat because creating a user stamps a revocation not-before, and a
        # token carrying no issue time to compare against it fails closed. Every
        # real openIMIS token carries nbf, so this only makes the fixture match
        # what the encoder actually emits.
        token = _sign(
            jwt_settings.JWT_SECRET_KEY, username="authNoSalt", iat=_exp(days=0)
        )

        self.assertEqual(decode(token)["username"], "authNoSalt")

    def test_unsigned_token_is_rejected(self):
        token = _sign(token_hex(32), username="authLegacy")

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)


class LegacyTokenRejectedTest(TestCase):
    """The migration window is closed: a token signed with the per-user salt
    carries no kid, and nothing routes it any more.
    """

    def setUp(self):
        self.password = _password()
        self.user = create_test_interactive_user(
            username="authLegacyGone", password=self.password
        )

    def test_a_token_signed_with_the_user_salt_is_rejected(self):
        token = _sign(self.user.i_user.private_key, username=self.user.username)

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)

    def test_a_token_signed_with_the_deployment_wide_secret_is_rejected(self):
        # The second legacy regime: a user with no salt was signed with
        # SECRET_KEY, which is what made forging one only as hard as that value.
        token = _sign(jwt_settings.JWT_SECRET_KEY, username=self.user.username)

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)

    def test_rejecting_one_reads_no_user_row(self):
        # The legacy provider resolved its key from the unverified username.
        token = _sign(jwt_settings.JWT_SECRET_KEY, username=self.user.username)

        with self.assertNumQueries(0):
            with self.assertRaises(pyjwt.InvalidTokenError):
                decode(token)


@with_deployment_key
class DeploymentKeyDecodeTest(TestCase):
    """Tokens signed with the deployment keypair, selected by the kid header.

    The exception type matters as much as the rejection: anything that is not an
    InvalidTokenError reaches the client as a 500, not an auth failure.
    """

    def test_deployment_token_needs_one_query_for_the_revocation_check(self):
        # Key selection still touches no database. The single query is the
        # revocation check reading the user's not-before.
        token = _sign(DEPLOYMENT_KEY, kid=DEPLOYMENT_KID, username="noSuchUser")

        with self.assertNumQueries(1):
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

    def test_token_without_an_issue_time_is_rejected(self):
        # Every token the encoder emits carries iat (core/auth/encode.py), and
        # the legacy tokens that did not are rejected outright now. Requiring it
        # is what makes the fail-closed branch in assert_not_revoked unreachable.
        token = _sign(
            DEPLOYMENT_KEY, kid=DEPLOYMENT_KID, username="noSuchUser", iat=None
        )

        with self.assertRaises(pyjwt.MissingRequiredClaimError):
            decode(token)

    def test_token_without_username_is_rejected(self):
        token = _sign(DEPLOYMENT_KEY, kid=DEPLOYMENT_KID, sub="noSuchUser")

        with self.assertRaises(pyjwt.MissingRequiredClaimError):
            decode(token)


class NoDeploymentKeyConfiguredTest(TestCase):
    """The default state: no keypair provisioned, so no kid resolves."""

    def test_kid_token_is_rejected_when_no_key_is_provisioned(self):
        token = _sign(DEPLOYMENT_KEY, kid=DEPLOYMENT_KID, username="noSuchUser")

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)

    def test_legacy_tokens_still_work(self):
        password = _password()
        user = create_test_interactive_user(username="authNoKey", password=password)
        token = get_token(user, DummyContext(user=user))

        self.assertEqual(decode(token)["username"], user.username)
