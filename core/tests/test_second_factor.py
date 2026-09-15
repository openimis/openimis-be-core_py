import time

from django.test import TestCase
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.auth import devices
from core.models import User
from core.test_helpers import create_test_interactive_user


def _code(device, offset=0):
    """A token as the authenticator app would render it: zero-padded to the
    device's digit count. TOTP.token() returns an int, so 0012 would otherwise
    be submitted as 12."""
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    totp.time = time.time() + offset * device.step
    return f"{totp.token():0{device.digits}d}"


class SecondFactorDevicesTest(TestCase):
    def setUp(self):
        create_test_interactive_user(username="otp_user")
        self.user = User.objects.get(username="otp_user")

    def test_enrolment_starts_unconfirmed(self):
        device = devices.enrol_totp(self.user)
        self.assertFalse(device.confirmed)
        self.assertFalse(devices.has_second_factor(self.user))
        self.assertEqual(devices.confirmed_devices(self.user), [])

    def test_confirming_with_a_valid_code_activates_the_device(self):
        device = devices.enrol_totp(self.user)
        self.assertTrue(devices.confirm_totp(device, _code(device)))
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertTrue(devices.has_second_factor(self.user))

    def test_confirming_with_a_wrong_code_leaves_it_unconfirmed(self):
        device = devices.enrol_totp(self.user)
        self.assertFalse(devices.confirm_totp(device, "000000"))
        device.refresh_from_db()
        self.assertFalse(device.confirmed)

    def test_re_enrolling_discards_the_abandoned_unconfirmed_device(self):
        first = devices.enrol_totp(self.user)
        second = devices.enrol_totp(self.user)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)

    def test_issuing_recovery_codes_returns_them_once_and_stores_them(self):
        codes = devices.issue_recovery_codes(self.user)
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        device = StaticDevice.objects.get(user=self.user)
        self.assertEqual(
            sorted(device.token_set.values_list("token", flat=True)), sorted(codes)
        )

    def test_re_issuing_replaces_the_previous_set(self):
        old = devices.issue_recovery_codes(self.user)
        new = devices.issue_recovery_codes(self.user)
        self.assertEqual(StaticDevice.objects.filter(user=self.user).count(), 1)
        stored = set(
            StaticDevice.objects.get(user=self.user)
            .token_set.values_list("token", flat=True)
        )
        self.assertEqual(stored, set(new))
        self.assertFalse(stored & set(old))

    def test_removing_everything_leaves_no_second_factor(self):
        device = devices.enrol_totp(self.user)
        devices.confirm_totp(device, _code(device))
        devices.issue_recovery_codes(self.user)
        devices.remove_all(self.user)
        self.assertFalse(devices.has_second_factor(self.user))
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())
