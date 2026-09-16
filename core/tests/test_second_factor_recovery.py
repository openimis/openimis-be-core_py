"""Getting back into an account whose second factor is lost.

Two ways, and the tests keep them unequal: a user who still holds a device
re-issues their own recovery codes, while a user who holds nothing needs an
administrator whose action is gated, recorded and ends every session.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from graphql_jwt.refresh_token.shortcuts import create_refresh_token
from rest_framework.exceptions import AuthenticationFailed

from core.auth import devices, recovery
from core.models import User
from core.test_helpers import (
    create_test_interactive_user,
    create_test_role,
    create_test_technical_user,
)
from core.tests.test_auth_revocation import _now, _stored_not_before
from core.tests.test_login_flow import _enrol, _password


def _codes_stored(user):
    return set(
        StaticToken.objects.filter(device__user=user).values_list("token", flat=True)
    )


class ResetSecondFactorTest(TestCase):
    """The service. Who may call it, what it removes, what it ends."""

    @classmethod
    def setUpTestData(cls):
        # Explicit roles throughout: the helper's default is the IMIS
        # Administrator role plus is_superuser, which holds every right.
        cls.resetter_role = create_test_role(
            perm_names=["gql_mutation_reset_second_factor_perms"],
            name="Second-factor resetter",
        )
        cls.updater_role = create_test_role(
            perm_names=["gql_mutation_update_users_perms"], name="User updater"
        )
        cls.resetter = create_test_interactive_user(
            username="mfaResetter", password=_password(), roles=[cls.resetter_role.id]
        )
        cls.updater = create_test_interactive_user(
            username="mfaUpdater", password=_password(), roles=[cls.updater_role.id]
        )
        cls.superuser = create_test_interactive_user(
            username="mfaSuper", password=_password()
        )

    def setUp(self):
        self.target = create_test_interactive_user(
            username="mfaTarget", password=_password(), roles=[]
        )
        _enrol(self.target)
        devices.issue_recovery_codes(self.target)

    def test_the_right_alone_is_enough(self):
        recovery.reset_second_factor(self.resetter, self.target.id)

        self.assertFalse(devices.has_second_factor(self.target))

    def test_a_superuser_holds_the_right_implicitly(self):
        recovery.reset_second_factor(self.superuser, self.target.id)

        self.assertFalse(devices.has_second_factor(self.target))

    def test_the_update_users_right_is_not_this_right(self):
        with self.assertRaises(AuthenticationFailed):
            recovery.reset_second_factor(self.updater, self.target.id)

        self.assertTrue(devices.has_second_factor(self.target))
        self.assertEqual(len(_codes_stored(self.target)), 10)

    def test_every_device_class_goes_confirmed_or_not(self):
        devices.enrol_totp(self.target, name="abandoned")

        recovery.reset_second_factor(self.resetter, self.target.id)

        self.assertEqual(TOTPDevice.objects.filter(user=self.target).count(), 0)
        self.assertEqual(StaticDevice.objects.filter(user=self.target).count(), 0)
        self.assertEqual(_codes_stored(self.target), set())

    def test_the_not_before_moves_so_older_tokens_stop(self):
        before = _now()

        recovery.reset_second_factor(self.resetter, self.target.id)

        self.assertGreaterEqual(_stored_not_before(self.target), before)

    def test_refresh_tokens_are_revoked(self):
        refresh = create_refresh_token(self.target)

        recovery.reset_second_factor(self.resetter, self.target.id)

        refresh.refresh_from_db()
        self.assertIsNotNone(refresh.revoked)

    def test_the_caller_is_untouched(self):
        _enrol(self.resetter)

        recovery.reset_second_factor(self.resetter, self.target.id)

        self.assertTrue(devices.has_second_factor(self.resetter))

    def test_a_technical_user_is_refused_because_sessions_cannot_be_ended(self):
        # A technical user has no interactive row and so no not-before.
        # Removing the devices while every session stays alive is the
        # half-reset this refuses to leave behind.
        technical = create_test_technical_user(username="mfaTechnical")
        core_user = User.objects.get(username=technical.username)
        _enrol(core_user)

        with self.assertRaises(ValidationError):
            recovery.reset_second_factor(self.resetter, core_user.id)

        self.assertTrue(devices.has_second_factor(core_user))

    def test_a_uuid_that_is_nobody_is_an_error_not_a_silent_success(self):
        with self.assertRaises(User.DoesNotExist):
            recovery.reset_second_factor(
                self.resetter, "00000000-0000-0000-0000-000000000000"
            )
