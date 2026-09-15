import json
from secrets import token_hex

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.exceptions import AuthenticationFailed

from core.auth import devices
from core.auth.login import (
    INVALID_SECOND_FACTOR,
    SECOND_FACTOR_REQUIRED,
    SECOND_FACTOR_THROTTLED,
    SecondFactorError,
    authenticate_login,
)
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from core.tests.test_second_factor import _code


def _password():
    """Generated, so no password-shaped literal ends up in the repository."""
    return token_hex(16) + "Aa1!"


def _request():
    """A request with a real, empty session - what open_admin_session needs."""
    request = RequestFactory().post("/api/graphql")
    SessionMiddleware(lambda r: None).process_request(request)
    return request


def _enrol(user):
    """A confirmed TOTP device, with the replay floor rewound.

    Confirming consumes the time step whose code was used, and a genuine login
    happens in a later step than the enrolment it follows - rewind rather than
    make every test here wait 30 seconds. The property itself is pinned by
    test_second_factor.test_the_code_that_confirmed_cannot_also_log_in.
    """
    device = devices.enrol_totp(user)
    assert devices.confirm_totp(device, _code(device))
    TOTPDevice.objects.filter(pk=device.pk).update(last_t=-1)
    device.refresh_from_db()
    return device


class AuthenticateLoginTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.user = create_test_interactive_user(
            username="loginFlowUser", password=cls.password
        )

    def test_a_user_without_a_device_logs_in_on_the_password_alone(self):
        user = authenticate_login(_request(), self.user.username, self.password)
        self.assertEqual(user.pk, self.user.pk)

    def test_a_stray_code_from_an_unenrolled_user_is_ignored(self):
        user = authenticate_login(
            _request(), self.user.username, self.password, otp="123456"
        )
        self.assertEqual(user.pk, self.user.pk)

    def test_a_wrong_password_fails_before_the_second_factor_is_looked_at(self):
        _enrol(self.user)
        with self.assertRaises(AuthenticationFailed):
            authenticate_login(_request(), self.user.username, "not-it", otp="123456")

    def test_an_enrolled_user_without_a_code_is_asked_for_one(self):
        _enrol(self.user)
        with self.assertRaises(SecondFactorError) as raised:
            authenticate_login(_request(), self.user.username, self.password)
        self.assertEqual(raised.exception.code, SECOND_FACTOR_REQUIRED)
        self.assertEqual(str(raised.exception), SECOND_FACTOR_REQUIRED)

    def test_an_enrolled_user_with_a_code_logs_in(self):
        device = _enrol(self.user)
        user = authenticate_login(
            _request(), self.user.username, self.password, otp=_code(device)
        )
        self.assertEqual(user.pk, self.user.pk)

    def test_a_recovery_code_logs_in_too(self):
        _enrol(self.user)
        codes = devices.issue_recovery_codes(self.user)
        user = authenticate_login(
            _request(), self.user.username, self.password, otp=codes[0]
        )
        self.assertEqual(user.pk, self.user.pk)

    def test_a_named_device_is_honoured(self):
        device = _enrol(self.user)
        user = authenticate_login(
            _request(), self.user.username, self.password,
            otp=_code(device), otp_device=device.persistent_id,
        )
        self.assertEqual(user.pk, self.user.pk)

    def test_a_wrong_code_is_invalid(self):
        _enrol(self.user)
        with self.assertRaises(SecondFactorError) as raised:
            authenticate_login(
                _request(), self.user.username, self.password, otp="000000"
            )
        self.assertEqual(raised.exception.code, INVALID_SECOND_FACTOR)
        self.assertEqual(raised.exception.extensions, {"code": INVALID_SECOND_FACTOR})

    def test_someone_elses_device_reads_as_invalid_not_as_missing(self):
        device = _enrol(self.user)
        other = create_test_interactive_user(
            username="loginFlowOther", password=self.password
        )
        _enrol(other)
        with self.assertRaises(SecondFactorError) as raised:
            authenticate_login(
                _request(), other.username, self.password,
                otp=_code(device), otp_device=device.persistent_id,
            )
        self.assertEqual(raised.exception.code, INVALID_SECOND_FACTOR)

    def test_a_throttled_device_reports_when_it_lifts(self):
        _enrol(self.user)
        with self.assertRaises(SecondFactorError):
            authenticate_login(
                _request(), self.user.username, self.password, otp="000000"
            )
        # Back-off starts at one second after the first failure, so an
        # immediate retry is refused without being tried.
        with self.assertRaises(SecondFactorError) as raised:
            authenticate_login(
                _request(), self.user.username, self.password, otp="000000"
            )
        self.assertEqual(raised.exception.code, SECOND_FACTOR_THROTTLED)
        self.assertTrue(raised.exception.extensions["lockedUntil"])


TOKEN_AUTH = """
    mutation login($username: String!, $password: String!, $otp: String, $otpDevice: String) {
        tokenAuth(username: $username, password: $password, otp: $otp, otpDevice: $otpDevice) {
            token
        }
    }
"""


class TokenAuthSecondFactorTest(openIMISGraphQLTestCase):
    """The contract the frontend builds against: HTTP 200, the code in
    errors[0].message, detail in errors[0].extensions - the shape
    INCORRECT_CREDENTIALS already has."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = _password()
        cls.user = create_test_interactive_user(
            username="tokenAuthOtp", password=cls.password
        )

    def _login(self, **variables):
        response = self.query(
            TOKEN_AUTH,
            variables={
                "username": self.user.username,
                "password": self.password,
                **variables,
            },
        )
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def test_an_unenrolled_user_logs_in_as_before(self):
        content = self._login()
        self.assertNotIn("errors", content)
        self.assertTrue(content["data"]["tokenAuth"]["token"])

    def test_an_enrolled_user_without_a_code_is_told_to_send_one(self):
        _enrol(self.user)
        content = self._login()
        self.assertEqual(content["errors"][0]["message"], SECOND_FACTOR_REQUIRED)
        self.assertEqual(
            content["errors"][0]["extensions"]["code"], SECOND_FACTOR_REQUIRED
        )
        self.assertIsNone(content["data"]["tokenAuth"])

    def test_an_enrolled_user_with_a_code_gets_a_token(self):
        device = _enrol(self.user)
        content = self._login(otp=_code(device))
        self.assertNotIn("errors", content)
        self.assertTrue(content["data"]["tokenAuth"]["token"])

    def test_a_named_device_is_accepted(self):
        device = _enrol(self.user)
        content = self._login(otp=_code(device), otpDevice=device.persistent_id)
        self.assertNotIn("errors", content)
        self.assertTrue(content["data"]["tokenAuth"]["token"])

    def test_a_wrong_code_mints_no_token_and_opens_no_session(self):
        # A non-staff user would pass the session half for the wrong reason.
        self.assertTrue(self.user.is_staff)
        _enrol(self.user)
        content = self._login(otp="000000")
        self.assertEqual(content["errors"][0]["message"], INVALID_SECOND_FACTOR)
        self.assertIsNone(content["data"]["tokenAuth"])
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_a_throttled_attempt_says_when_it_lifts(self):
        _enrol(self.user)
        self._login(otp="000000")
        content = self._login(otp="000000")
        self.assertEqual(content["errors"][0]["message"], SECOND_FACTOR_THROTTLED)
        self.assertTrue(content["errors"][0]["extensions"]["lockedUntil"])
