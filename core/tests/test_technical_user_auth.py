from dataclasses import dataclass
from secrets import token_hex

import jwt as pyjwt
from django.test import TestCase, override_settings
from graphql_jwt.shortcuts import get_token

from core.auth import decode
from core.models import TechnicalUser, User


@dataclass
class DummyContext:
    user: User


def _password():
    return token_hex(16) + "Aa1!"


def _technical_user(username):
    """Not create_test_technical_user: until step 8 that helper stores the
    password unhashed, so its user cannot authenticate.
    """
    t_user = TechnicalUser(username=username, email=f"{username}@openimis.org")
    t_user.set_password(_password())
    t_user.save()
    return User.objects.get(t_user=t_user)


class TechnicalUserTokenTest(TestCase):
    """Issuing a token for an account with no InteractiveUser row - what the
    per-user signing key made impossible, because the encoder resolved its key
    by looking one up.
    """

    def test_a_technical_user_obtains_a_token(self):
        user = _technical_user("techIssue")

        token = get_token(user, DummyContext(user=user))

        self.assertIsNotNone(token)

    def test_the_token_round_trips(self):
        user = _technical_user("techRoundTrip")

        token = get_token(user, DummyContext(user=user))

        self.assertEqual(decode(token)["username"], "techRoundTrip")

    def test_the_token_is_signed_with_the_deployment_key(self):
        user = _technical_user("techKid")

        token = get_token(user, DummyContext(user=user))

        self.assertIsNotNone(pyjwt.get_unverified_header(token).get("kid"))

    @override_settings(JWT_SIGNING_KEY=None)
    def test_issuing_without_a_key_refuses_rather_than_falling_back(self):
        # Before the gate came out this reached the per-user path and raised
        # InteractiveUser.DoesNotExist. There is no second path to fall to now,
        # and the startup check is what stops a deployment getting here at all.
        user = _technical_user("techNoKey")

        with self.assertRaises(ValueError) as caught:
            get_token(user, DummyContext(user=user))

        self.assertIn("JWT_SIGNING_KEY", str(caught.exception))

    def test_issuing_touches_no_interactive_user(self):
        # The whole defect: the old encoder resolved its key through
        # InteractiveUser.objects.get(login_name=...) and raised DoesNotExist.
        user = _technical_user("techNoLookup")

        with self.assertNumQueries(0):
            get_token(user, DummyContext(user=user))
