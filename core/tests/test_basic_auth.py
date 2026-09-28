import base64
from secrets import token_hex

from axes.models import AccessAttempt
from django.test import RequestFactory, TestCase
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.exceptions import AuthenticationFailed

from core.auth import devices
from core.auth.basic import SecondFactorBasicAuthentication
from core.auth.login import SECOND_FACTOR_REQUIRED
from core.test_helpers import (
    create_test_interactive_user,
    create_test_technical_user,
)
from core.tests.test_second_factor import _code


def _password():
    """Generated, so no password-shaped literal ends up in the repository."""
    return token_hex(16) + "Aa1!"


def _enrol(user):
    """A confirmed TOTP device, with the replay floor rewound.

    Confirming consumes the time step whose code was used; rewind rather than
    make every test wait 30 seconds. Pinned by
    test_second_factor.test_the_code_that_confirmed_cannot_also_log_in.
    """
    device = devices.enrol_totp(user)
    assert devices.confirm_totp(device, _code(device))
    TOTPDevice.objects.filter(pk=device.pk).update(last_t=-1)
    device.refresh_from_db()
    return device


def _request(username, password):
    """A GET carrying an HTTP Basic header, as a REST client would send it."""
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return RequestFactory().get(
        "/api/api_fhir_r4/Patient/", HTTP_AUTHORIZATION=f"Basic {encoded}"
    )


def _failures(username):
    attempt = AccessAttempt.objects.filter(username=username).first()
    return attempt.failures_since_start if attempt else 0


class SecondFactorBasicAuthenticationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.user = create_test_interactive_user(
            username="basicAuthUser", password=cls.password
        )

    def test_an_enrolled_user_is_refused(self):
        _enrol(self.user)
        with self.assertRaises(AuthenticationFailed) as caught:
            SecondFactorBasicAuthentication().authenticate(
                _request("basicAuthUser", self.password)
            )
        self.assertEqual(str(caught.exception.detail), SECOND_FACTOR_REQUIRED)

    def test_an_unenrolled_user_is_accepted(self):
        user, _auth = SecondFactorBasicAuthentication().authenticate(
            _request("basicAuthUser", self.password)
        )
        self.assertEqual(user.pk, self.user.pk)

    def test_a_wrong_password_is_still_refused(self):
        _enrol(self.user)
        with self.assertRaises(AuthenticationFailed) as caught:
            SecondFactorBasicAuthentication().authenticate(
                _request("basicAuthUser", _password())
            )
        # Not SECOND_FACTOR_REQUIRED: answering differently to a wrong password
        # and to an enrolled user would let the header enumerate who is enrolled.
        self.assertNotEqual(str(caught.exception.detail), SECOND_FACTOR_REQUIRED)

    def test_a_header_this_class_does_not_own_is_passed_through(self):
        request = RequestFactory().get("/api/api_fhir_r4/Patient/")
        self.assertIsNone(SecondFactorBasicAuthentication().authenticate(request))

    def test_a_refusal_for_a_missing_factor_is_not_a_failed_login(self):
        # The password was right; being asked for a factor is not guessing.
        _enrol(self.user)
        with self.assertRaises(AuthenticationFailed):
            SecondFactorBasicAuthentication().authenticate(
                _request("basicAuthUser", self.password)
            )
        self.assertEqual(_failures("basicAuthUser"), 0)

    def test_a_wrong_password_is_a_failed_login(self):
        with self.assertRaises(AuthenticationFailed):
            SecondFactorBasicAuthentication().authenticate(
                _request("basicAuthUser", _password())
            )
        self.assertEqual(_failures("basicAuthUser"), 1)


class TechnicalUserBasicAuthenticationTest(TestCase):
    """The integrations are why Basic stays enabled at all."""

    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.user = create_test_technical_user(
            username="basicAuthTech", password=cls.password
        )

    def test_a_technical_user_is_accepted(self):
        user, _auth = SecondFactorBasicAuthentication().authenticate(
            _request("basicAuthTech", self.password)
        )
        self.assertEqual(user.username, "basicAuthTech")
