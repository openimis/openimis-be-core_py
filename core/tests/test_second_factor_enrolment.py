"""Enrolling an authenticator, for a user who cannot log in yet.

The tests keep both mutations on the password's footing - no session, no
token before the device is confirmed - and refuse them to whoever already
has a device.
"""

from django.test import TestCase
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.exceptions import AuthenticationFailed

from core.auth import devices, enrolment
from core.auth.enrolment import SECOND_FACTOR_ALREADY_ENROLLED
from core.auth.login import SecondFactorError
from core.models import User
from core.test_helpers import (
    create_test_interactive_user,
    create_test_technical_user,
)
from core.tests.test_login_flow import _enrol, _password, _request


class BeginEnrolmentTest(TestCase):
    """The service: what the password buys, and whom it refuses."""

    def setUp(self):
        self.password = _password()
        self.user = create_test_interactive_user(
            username="enrolBegin", password=self.password, roles=[]
        )

    def _begin(self, password=None, username=None):
        return enrolment.begin(
            _request(), username or self.user.username, password or self.password
        )

    def test_the_password_buys_an_unconfirmed_authenticator(self):
        device = self._begin()

        self.assertFalse(device.confirmed)
        self.assertEqual(device.user_id, self.user.pk)
        self.assertFalse(devices.has_second_factor(self.user))
        self.assertIn("secret=" + enrolment.secret(device), device.config_url)

    def test_a_wrong_password_is_refused_and_creates_nothing(self):
        with self.assertRaises(AuthenticationFailed):
            self._begin(password="not-the-password")

        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())

    def test_a_user_who_already_has_a_device_is_refused(self):
        _enrol(self.user)

        with self.assertRaises(SecondFactorError) as raised:
            self._begin()

        self.assertEqual(raised.exception.code, SECOND_FACTOR_ALREADY_ENROLLED)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)

    def test_beginning_again_replaces_the_pending_device(self):
        first = self._begin()
        second = self._begin()

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(devices.pending_totp(self.user).pk, second.pk)

    def test_a_technical_user_can_enrol(self):
        # A privileged technical account is bound under per_role and
        # mandatory (policy._is_privileged), so it needs this path too.
        password = _password()
        technical = create_test_technical_user(
            username="enrolTechnical", password=password, staff=True
        )
        core_user = User.objects.get(username=technical.username)

        device = self._begin(username=core_user.username, password=password)

        self.assertEqual(device.user_id, core_user.pk)
