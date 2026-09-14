from dataclasses import dataclass
from datetime import timedelta
from secrets import token_hex

import jwt as pyjwt
from django.test import TestCase, override_settings
from django.utils import timezone
from graphql_jwt import exceptions as jwt_exceptions
from graphql_jwt.shortcuts import get_token
from graphql_jwt.utils import get_payload, get_user_by_payload, refresh_has_expired

from core.access import has_role_perms

from core.auth import decode
from core.models import User
from core.test_helpers import create_test_technical_user


@dataclass
class DummyContext:
    user: User


def _password():
    return token_hex(16) + "Aa1!"


def _technical_user(username):
    return create_test_technical_user(username=username, password=_password())


class TechnicalUserFixtureTest(TestCase):
    """The shared fixture stored the password unhashed, so every user it built
    failed check_password - a trap for anything testing this path.
    """

    def test_the_fixture_user_can_authenticate(self):
        password = _password()

        user = create_test_technical_user(username="techFixture", password=password)

        self.assertTrue(user.check_password(password))


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


class TechnicalUserRevocationBoundaryTest(TestCase):
    """The gap this ticket accepts rather than closes.

    Revocation is a not-before stored in InteractiveUser.json_ext, and a
    technical user has no InteractiveUser row and no JSON column of its own, so
    nothing records one. Each test below is a decision, not an oversight - see
    the task file's decision 1.
    """

    def test_a_token_survives_a_password_change_by_design(self):
        user = _technical_user("techRotate")
        token = get_token(user, DummyContext(user=user))

        user.t_user.set_password(_password())
        user.t_user.save()

        self.assertEqual(decode(token)["username"], "techRotate")

    def test_the_refresh_window_outlives_the_password_change_too(self):
        # What makes the exposure 30 days rather than one: refreshToken
        # re-issues from the token itself (graphql_jwt.mixins.RefreshMixin),
        # and decode has no not-before to refuse it with.
        user = _technical_user("techRefresh")
        token = get_token(user, DummyContext(user=user))

        user.t_user.set_password(_password())
        user.t_user.save()

        payload = get_payload(token)
        self.assertFalse(refresh_has_expired(payload["origIat"]))
        self.assertIsNotNone(get_user_by_payload(payload))

    def test_time_bounding_the_account_does_end_it(self):
        # The one lever that works: is_active reads validity_to for a technical
        # user, and get_user_by_payload rejects an inactive one.
        user = _technical_user("techExpire")
        token = get_token(user, DummyContext(user=user))

        user.t_user.validity_to = timezone.now() - timedelta(days=1)
        user.t_user.save()

        with self.assertRaises(jwt_exceptions.JSONWebTokenError):
            get_user_by_payload(get_payload(token))


class TechnicalUserRightsTest(TestCase):
    """Pre-existing behaviour, pinned because this ticket is what first lets a
    technical user hold a token to exercise it.
    """

    def test_a_technical_user_holds_no_rights(self):
        user = _technical_user("techRights")

        self.assertEqual(user.rights, [])
        self.assertFalse(has_role_perms(user, ["121901"]))

    def test_the_technical_user_superuser_flag_does_not_reach_the_check(self):
        # TechnicalUser.is_superuser does NOT escalate: core.User inherits
        # PermissionsMixin, so is_superuser is a column on core_User too, and
        # __getattr__ never delegates to t_user for a name that resolves. Nor
        # does _bind_User copy it.
        user = create_test_technical_user(
            username="techSuper", password=_password(), super_user=True
        )

        self.assertTrue(user.t_user.is_superuser)
        self.assertFalse(user.is_superuser)
        self.assertFalse(has_role_perms(user, ["121901"]))

    def test_the_core_user_superuser_flag_does(self):
        # The escalation is real but needs a deliberate write to core_User,
        # which no openIMIS code path performs for a technical user. Pinned so
        # the boundary is on record rather than assumed.
        user = _technical_user("techSuperCore")
        user.is_superuser = True
        user.save()

        self.assertEqual(user.rights, [])
        self.assertTrue(has_role_perms(user, ["121901"]))
