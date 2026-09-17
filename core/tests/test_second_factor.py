import time
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.auth import devices, second_factor
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

    def test_the_pending_device_is_the_one_scanned_and_not_yet_confirmed(self):
        self.assertIsNone(devices.pending_totp(self.user))
        device = devices.enrol_totp(self.user)
        self.assertEqual(devices.pending_totp(self.user).pk, device.pk)
        devices.confirm_totp(device, _code(device))
        self.assertIsNone(devices.pending_totp(self.user))


class SecondFactorVerifyTest(TestCase):
    def setUp(self):
        create_test_interactive_user(username="otp_verify")
        self.user = User.objects.get(username="otp_verify")
        self.totp = devices.enrol_totp(self.user)
        devices.confirm_totp(self.totp, _code(self.totp))
        # Confirming *consumes* the time step whose code was used - the replay
        # floor is `last_t + 1`, and that is a real property, pinned by
        # test_the_code_that_confirmed_cannot_also_log_in below. A genuine login
        # happens in a later step than the enrolment it follows, so rewind the
        # floor rather than make every test here wait 30 seconds.
        TOTPDevice.objects.filter(pk=self.totp.pk).update(last_t=-1)
        self.totp.refresh_from_db()

    def test_the_code_that_confirmed_cannot_also_log_in(self):
        """Enrolment is not a free first login. Fresh device, so the rewind in
        setUp is undone here on purpose."""
        device = devices.enrol_totp(self.user, name="Second phone")
        code = _code(device)
        self.assertTrue(devices.confirm_totp(device, code))
        replay = second_factor.verify(
            self.user, code, device_id=device.persistent_id
        )
        self.assertFalse(replay.ok)
        self.assertEqual(replay.outcome, second_factor.INVALID)

    def test_a_valid_code_verifies_and_names_the_device(self):
        result = second_factor.verify(self.user, _code(self.totp))
        self.assertTrue(result.ok)
        self.assertEqual(result.outcome, second_factor.VERIFIED)
        self.assertEqual(result.device.persistent_id, self.totp.persistent_id)

    def test_a_reused_code_is_rejected(self):
        code = _code(self.totp)
        self.assertTrue(second_factor.verify(self.user, code).ok)
        replay = second_factor.verify(self.user, code)
        self.assertFalse(replay.ok)
        self.assertEqual(replay.outcome, second_factor.INVALID)

    def test_a_code_one_step_old_is_tolerated_and_the_drift_remembered(self):
        # tolerance defaults to 1 step, which is the clock-drift allowance the
        # ticket asks django-otp to provide; OTP_TOTP_SYNC (default True) then
        # records the offset that matched, so a consistently slow phone is not
        # re-tolerated from scratch on every login.
        self.assertTrue(second_factor.verify(self.user, _code(self.totp, -1)).ok)
        self.totp.refresh_from_db()
        self.assertEqual(self.totp.drift, -1)

    def test_a_recovery_code_verifies_and_is_consumed(self):
        codes = devices.issue_recovery_codes(self.user)
        result = second_factor.verify(self.user, codes[0])
        self.assertTrue(result.ok)
        self.assertIsInstance(result.device, StaticDevice)
        self.assertFalse(second_factor.verify(self.user, codes[0]).ok)
        self.assertEqual(
            StaticDevice.objects.get(user=self.user).token_set.count(), len(codes) - 1
        )

    def test_a_recovery_code_verifies_in_any_case_and_around_whitespace(self):
        """Static tokens are lowercase base32 matched exactly, so without
        normalising, a code retyped in upper case fails *and* burns a throttle
        failure on every device - a user locking themselves out by typing."""
        codes = devices.issue_recovery_codes(self.user)

        result = second_factor.verify(self.user, f"  {codes[0].upper()}  ")

        self.assertTrue(result.ok)
        self.assertIsInstance(result.device, StaticDevice)
        self.totp.refresh_from_db()
        self.assertEqual(self.totp.throttling_failure_count, 0)

    def test_a_recovery_code_does_not_throttle_the_authenticator(self):
        """The reason match_token is not used. The TOTP device is tried first and
        fails, and without the collateral reset it would back off exponentially
        every time the user fell back to a recovery code."""
        codes = devices.issue_recovery_codes(self.user)
        self.assertTrue(second_factor.verify(self.user, codes[0]).ok)
        self.totp.refresh_from_db()
        self.assertEqual(self.totp.throttling_failure_count, 0)
        self.assertIsNone(self.totp.throttling_failure_timestamp)

    def test_a_fallback_login_does_not_clear_an_existing_back_off(self):
        """Restore, not reset. throttle_reset() zeroes the counter, so clearing
        outright would let each legitimate recovery-code login wipe a back-off an
        attacker had built up on the authenticator - handing them a fresh budget
        every time the real user logged in."""
        codes = devices.issue_recovery_codes(self.user)
        earlier = timezone.now() - timedelta(minutes=5)
        TOTPDevice.objects.filter(pk=self.totp.pk).update(
            throttling_failure_count=4, throttling_failure_timestamp=earlier
        )

        self.assertTrue(second_factor.verify(self.user, codes[0]).ok)

        self.totp.refresh_from_db()
        self.assertEqual(self.totp.throttling_failure_count, 4)
        self.assertEqual(self.totp.throttling_failure_timestamp, earlier)

    def test_a_wrong_code_throttles_every_device_it_was_tried_against(self):
        devices.issue_recovery_codes(self.user)
        result = second_factor.verify(self.user, "000000")
        self.assertEqual(result.outcome, second_factor.INVALID)
        self.totp.refresh_from_db()
        self.assertEqual(self.totp.throttling_failure_count, 1)
        self.assertEqual(
            StaticDevice.objects.get(user=self.user).throttling_failure_count, 1
        )

    def test_a_user_with_no_confirmed_device_reports_no_devices(self):
        create_test_interactive_user(username="otp_bare")
        bare = User.objects.get(username="otp_bare")
        self.assertEqual(
            second_factor.verify(bare, "000000").outcome, second_factor.NO_DEVICES
        )

    def test_every_device_throttled_reports_when_it_lifts(self):
        self.totp.throttling_failure_count = 3
        self.totp.throttling_failure_timestamp = timezone.now()
        self.totp.save()
        result = second_factor.verify(self.user, _code(self.totp))
        self.assertEqual(result.outcome, second_factor.THROTTLED)
        self.assertGreater(result.locked_until, timezone.now())
        self.assertLess(result.locked_until, timezone.now() + timedelta(minutes=1))

    def test_a_named_device_is_the_only_one_tried(self):
        codes = devices.issue_recovery_codes(self.user)
        static = StaticDevice.objects.get(user=self.user)
        result = second_factor.verify(
            self.user, codes[0], device_id=static.persistent_id
        )
        self.assertTrue(result.ok)
        self.totp.refresh_from_db()
        self.assertEqual(self.totp.throttling_failure_count, 0)

    def test_a_device_belonging_to_someone_else_is_refused(self):
        create_test_interactive_user(username="otp_other")
        other = User.objects.get(username="otp_other")
        result = second_factor.verify(
            other, _code(self.totp), device_id=self.totp.persistent_id
        )
        self.assertEqual(result.outcome, second_factor.NO_DEVICES)

    def test_a_malformed_device_id_is_no_such_device_not_a_crash(self):
        """django-otp suppresses ValueError and LookupError, so a nonsense id is
        already safe - but an id naming a real non-Device model leaves it calling
        .first() on None, and a non-string id has no .rsplit. The login flow passes
        this value straight from a client, so neither may be a 500."""
        for bad in [
            "core.user/1",       # a real model, not a Device subclass
            "core.user/abc",     # same, and an unparseable pk
            "nosuchapp.model/1",  # LookupError, already suppressed upstream
            "nodelimiter",       # ValueError, already suppressed upstream
            "",
            12345,               # not a string at all
        ]:
            with self.subTest(device_id=bad):
                result = second_factor.verify(self.user, "000000", device_id=bad)
                self.assertEqual(result.outcome, second_factor.NO_DEVICES)

    def test_an_unconfirmed_device_cannot_be_named_either(self):
        create_test_interactive_user(username="otp_pending")
        pending_user = User.objects.get(username="otp_pending")
        pending = devices.enrol_totp(pending_user)
        result = second_factor.verify(
            pending_user, _code(pending), device_id=pending.persistent_id
        )
        self.assertEqual(result.outcome, second_factor.NO_DEVICES)
