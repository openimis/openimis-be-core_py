"""Enrolling an authenticator, for a user who cannot log in yet.

Most tests run under a policy that binds the user, which is the situation the
password-only path exists for: no session, no token before the device is
confirmed, and a refusal for whoever already has a device. EnrolmentGateTest
covers a user the policy leaves free, who needs their own login as well.
"""

import json
from unittest.mock import patch

from axes.models import AccessAttempt
from django.test import TestCase
from graphql.error import GraphQLError
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.exceptions import AuthenticationFailed

from core.auth import devices, enrolment, policy
from core.auth.enrolment import (
    SECOND_FACTOR_ALREADY_ENROLLED,
    SECOND_FACTOR_LOGIN_REQUIRED,
)
from core.auth.login import (
    INVALID_SECOND_FACTOR,
    SECOND_FACTOR_ENROLMENT_REQUIRED,
    SECOND_FACTOR_REQUIRED,
    SECOND_FACTOR_THROTTLED,
    SecondFactorError,
    authenticate_login,
)
from core.models import MutationLog, User
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import (
    create_test_interactive_user,
    create_test_technical_user,
)
from core.tests.test_login_flow import (
    TOKEN_AUTH,
    _enrol,
    _password,
    _request,
    _throttle,
)
from core.tests.test_second_factor import _code
from core.tests.test_second_factor_policy import _policy
from core.tests.test_second_factor_recovery import _codes_stored


def _bound(test):
    """Bind every interactive user for the rest of the test: they cannot log
    in until they enrol, so the password alone is what enrolment runs on."""
    patcher = _policy(policy.MANDATORY)
    patcher.start()
    test.addCleanup(patcher.stop)


def _failures(username):
    """axes' count for the account - the sibling suite's measure."""
    attempt = AccessAttempt.objects.filter(username=username).first()
    return attempt.failures_since_start if attempt else 0


class BeginEnrolmentTest(TestCase):
    """The service: what the password buys, and whom it refuses."""

    def setUp(self):
        _bound(self)
        self.password = _password()
        self.user = create_test_interactive_user(
            username="enrolBegin", password=self.password, roles=[]
        )

    def _begin(self, password=None, username=None):
        return enrolment.begin(
            _request(),
            username or self.user.username,
            self.password if password is None else password,
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


class CompleteEnrolmentTest(TestCase):
    """The service: one code confirms, the codes come once, and nothing is a
    login until tokenAuth."""

    def setUp(self):
        _bound(self)
        self.password = _password()
        self.user = create_test_interactive_user(
            username="enrolComplete", password=self.password, roles=[]
        )
        self.device = enrolment.begin(_request(), self.user.username, self.password)

    def _complete(self, otp, password=None):
        return enrolment.complete(
            _request(),
            self.user.username,
            self.password if password is None else password,
            otp,
        )

    def test_the_devices_code_confirms_it_and_issues_the_first_recovery_set(self):
        codes = self._complete(_code(self.device))

        self.device.refresh_from_db()
        self.assertTrue(self.device.confirmed)
        self.assertTrue(devices.has_second_factor(self.user))
        self.assertEqual(len(codes), 10)
        self.assertEqual(_codes_stored(self.user), set(codes))

    def test_binding_a_factor_leaves_a_trace_in_the_log(self):
        # Nothing else records it - the mutations write no log row - and an
        # authenticator appearing on an account is worth being able to find.
        with self.assertLogs("core.auth.enrolment", level="INFO") as caught:
            self._complete(_code(self.device))

        self.assertTrue(
            any(self.user.username in line for line in caught.output), caught.output
        )

    def test_the_next_code_logs_in_and_the_confirming_one_does_not(self):
        # Confirmation is not a disguised login: the step it spent is below
        # the replay floor. The next step's code is what tokenAuth will take.
        # Order matters - the replay charges a throttle failure, so it goes
        # last or the valid attempt after it reads THROTTLED.
        confirming = _code(self.device)
        self._complete(confirming)
        self.device.refresh_from_db()

        user = authenticate_login(
            _request(), self.user.username, self.password,
            otp=_code(self.device, offset=1),
        )
        self.assertEqual(user.pk, self.user.pk)
        with self.assertRaises(SecondFactorError) as replay:
            authenticate_login(
                _request(), self.user.username, self.password, otp=confirming
            )
        self.assertEqual(replay.exception.code, INVALID_SECOND_FACTOR)

    def test_a_wrong_code_leaves_it_unconfirmed_and_issues_nothing(self):
        with self.assertRaises(SecondFactorError) as raised:
            self._complete("000000")

        self.assertEqual(raised.exception.code, INVALID_SECOND_FACTOR)
        self.device.refresh_from_db()
        self.assertFalse(self.device.confirmed)
        self.assertEqual(_codes_stored(self.user), set())

    def test_a_wrong_code_is_not_a_failed_login(self):
        with self.assertRaises(SecondFactorError):
            self._complete("000000")

        self.assertEqual(_failures(self.user.username), 0)

    def test_a_wrong_code_charges_the_device_and_the_back_off_then_bites(self):
        # The per-device back-off is the only thing metering a guess here - a
        # wrong code is deliberately not reported to the account lockout - so
        # the charge has to outlive the refusal that carries it. It would not
        # if the refusal were raised from inside the transaction.
        with self.assertRaises(SecondFactorError) as first:
            self._complete("000000")
        self.assertEqual(first.exception.code, INVALID_SECOND_FACTOR)

        self.device.refresh_from_db()
        self.assertEqual(self.device.throttling_failure_count, 1)

        with self.assertRaises(SecondFactorError) as second:
            self._complete("000000")
        self.assertEqual(second.exception.code, SECOND_FACTOR_THROTTLED)
        self.assertTrue(second.exception.extensions["lockedUntil"])

        # Refused without being tried, so the second guess is not charged.
        self.device.refresh_from_db()
        self.assertEqual(self.device.throttling_failure_count, 1)

    def test_an_empty_code_asks_for_one_without_charging_the_device(self):
        with self.assertRaises(SecondFactorError) as raised:
            self._complete("")

        self.assertEqual(raised.exception.code, SECOND_FACTOR_REQUIRED)
        self.device.refresh_from_db()
        self.assertEqual(self.device.throttling_failure_count, 0)

    def test_a_throttled_device_reports_when_it_lifts(self):
        _throttle(self.device)

        with self.assertRaises(SecondFactorError) as raised:
            self._complete(_code(self.device))

        self.assertEqual(raised.exception.code, SECOND_FACTOR_THROTTLED)
        self.assertTrue(raised.exception.extensions["lockedUntil"])
        self.device.refresh_from_db()
        self.assertFalse(self.device.confirmed)

    def test_nothing_pending_means_enrol_first(self):
        TOTPDevice.objects.filter(user=self.user).delete()

        with self.assertRaises(SecondFactorError) as raised:
            self._complete("000000")

        self.assertEqual(raised.exception.code, SECOND_FACTOR_ENROLMENT_REQUIRED)

    def test_a_stale_scan_cannot_be_completed_once_a_device_is_confirmed(self):
        # A confirmed device created outside enrol_totp, so the pending row
        # from setUp survives beside it - the state a shell, or a begin/confirm
        # race, can leave. The refusal is what keeps a QR code scanned before
        # any device existed from adding a second one afterwards.
        TOTPDevice.objects.create(user=self.user, name="phone", confirmed=True)

        with self.assertRaises(SecondFactorError) as raised:
            self._complete(_code(self.device))

        self.assertEqual(raised.exception.code, SECOND_FACTOR_ALREADY_ENROLLED)
        self.device.refresh_from_db()
        self.assertFalse(self.device.confirmed)

    def test_a_failure_issuing_codes_leaves_the_device_unconfirmed(self):
        # One transaction: a confirmed device with no recovery set is the
        # half-state this rules out. The user retries with the next code.
        with patch.object(devices, "issue_recovery_codes", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self._complete(_code(self.device))

        self.device.refresh_from_db()
        self.assertFalse(self.device.confirmed)

    def test_a_wrong_password_confirms_nothing(self):
        with self.assertRaises(AuthenticationFailed):
            self._complete(_code(self.device), password="not-the-password")

        self.device.refresh_from_db()
        self.assertFalse(self.device.confirmed)


ENROL = """
    mutation enrol($username: String!, $password: String!) {
        enrolSecondFactor(
            input: {username: $username, password: $password, clientMutationId: "enrol"}
        ) {
            method
            totp {
                configUrl
                secret
            }
            success
            error
        }
    }
"""


class EnrolSecondFactorMutationTest(openIMISGraphQLTestCase):
    """The GraphQL surface: the secret comes back, nothing is logged, and a
    wrong password is a failed login like any other."""

    def setUp(self):
        super().setUp()
        _bound(self)
        self.password = _password()
        self.user = create_test_interactive_user(
            username="enrolMutation", password=self.password, roles=[]
        )

    def _enrol(self, password=None):
        response = self.query(
            ENROL,
            variables={
                "username": self.user.username,
                # not `password or self.password`: an empty password is a case
                # under test, and would otherwise be swapped for the real one.
                "password": self.password if password is None else password,
            },
        )
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)["data"]["enrolSecondFactor"]

    def test_the_secret_comes_back_under_the_method_that_produced_it(self):
        payload = self._enrol()

        self.assertTrue(payload["success"], payload["error"])
        device = TOTPDevice.objects.get(user=self.user)
        self.assertFalse(device.confirmed)
        self.assertEqual(payload["method"], enrolment.TOTP)
        self.assertEqual(payload["totp"]["configUrl"], device.config_url)
        self.assertEqual(payload["totp"]["secret"], enrolment.secret(device))
        self.assertFalse(devices.has_second_factor(self.user))

    def test_a_channel_that_sends_the_code_adds_a_sibling_of_totp(self):
        """The payload names the method and carries that method's material
        under it, so a channel with nothing to scan is an added field rather
        than a changed one."""
        payload = self._enrol()

        self.assertEqual(set(payload), {"method", "totp", "success", "error"})
        self.assertEqual(set(payload["totp"]), {"configUrl", "secret"})

    def test_a_wrong_password_is_incorrect_credentials_and_a_failed_login(self):
        payload = self._enrol(password="not-the-password")

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "INCORRECT_CREDENTIALS")
        self.assertIsNone(payload["method"])
        self.assertIsNone(payload["totp"])
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        # Django's authenticate() sends user_login_failed; axes records it.
        # Nothing in the mutation does this - the test pins that nothing
        # undoes it either.
        self.assertEqual(_failures(self.user.username), 1)

    def test_a_missing_password_answers_the_way_the_login_does(self):
        # An empty string satisfies String!, so this reaches the service and
        # must not fall through to the generic handler as an unexpected error.
        payload = self._enrol(password="")

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "Missing username or password")
        self.assertIsNone(payload["totp"])
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())

    def test_a_user_with_a_device_is_refused(self):
        _enrol(self.user)

        payload = self._enrol()

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], SECOND_FACTOR_ALREADY_ENROLLED)
        self.assertIsNone(payload["totp"])

    def test_a_locked_out_address_is_told_so_and_gets_no_secret(self):
        # The lockout guards enrolment as it guards the login, or an address
        # refused at the login could still collect secrets here.
        with patch(
            "core.schema.check_lockout",
            side_effect=GraphQLError("Too many failed attempts.Try again in 5 minutes."),
        ):
            payload = self._enrol()

        self.assertFalse(payload["success"])
        self.assertIn("Too many failed attempts", payload["error"])
        self.assertIsNone(payload["totp"])
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())

    def test_nothing_reaches_the_mutation_log(self):
        before = MutationLog.objects.count()

        self._enrol()

        self.assertEqual(MutationLog.objects.count(), before)


CONFIRM = """
    mutation confirm($username: String!, $password: String!, $otp: String!) {
        confirmSecondFactor(
            input: {
                username: $username
                password: $password
                otp: $otp
                clientMutationId: "confirm"
            }
        ) {
            codes
            success
            error
            lockedUntil
        }
    }
"""


class ConfirmSecondFactorMutationTest(openIMISGraphQLTestCase):
    """The GraphQL surface, and the ticket's round trip: enrol, confirm, log
    in with the next code - and the same from a binding policy's refusal."""

    def setUp(self):
        super().setUp()
        _bound(self)
        self.password = _password()
        self.user = create_test_interactive_user(
            username="confirmMutation", password=self.password, roles=[]
        )
        self.device = enrolment.begin(_request(), self.user.username, self.password)

    def _confirm(self, otp):
        response = self.query(
            CONFIRM,
            variables={
                "username": self.user.username,
                "password": self.password,
                "otp": otp,
            },
        )
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)["data"]["confirmSecondFactor"]

    def _login(self, **variables):
        response = self.query(
            TOKEN_AUTH,
            variables={
                "username": self.user.username,
                "password": self.password,
                **variables,
            },
        )
        return json.loads(response.content)

    def test_the_code_confirms_and_the_first_recovery_set_comes_with_it(self):
        payload = self._confirm(_code(self.device))

        self.assertTrue(payload["success"], payload["error"])
        self.assertEqual(len(payload["codes"]), 10)
        self.assertEqual(_codes_stored(self.user), set(payload["codes"]))
        self.assertTrue(devices.has_second_factor(self.user))

    def test_enrol_then_confirm_then_log_in_with_the_next_code(self):
        payload = self._confirm(_code(self.device))
        self.assertTrue(payload["success"], payload["error"])

        # Enrolled now, so the password alone is refused - and nothing above
        # handed out a token to skip this with.
        refused = self._login()
        self.assertEqual(refused["errors"][0]["message"], SECOND_FACTOR_REQUIRED)

        self.device.refresh_from_db()
        content = self._login(otp=_code(self.device, offset=1))
        self.assertNotIn("errors", content)
        self.assertTrue(content["data"]["tokenAuth"]["token"])

        content = self._login(otp=payload["codes"][0])
        self.assertNotIn("errors", content)
        self.assertTrue(content["data"]["tokenAuth"]["token"])

    def test_a_bound_user_refused_at_login_enrols_from_that_refusal(self):
        # The case the ticket exists for: under a binding policy the login
        # refuses a user with no device, and this is the only way past it -
        # for someone with no token to present.
        with _policy(policy.MANDATORY):
            refused = self._login()
            self.assertEqual(
                refused["errors"][0]["message"], SECOND_FACTOR_ENROLMENT_REQUIRED
            )

            payload = self._confirm(_code(self.device))
            self.assertTrue(payload["success"], payload["error"])

            self.device.refresh_from_db()
            content = self._login(otp=_code(self.device, offset=1))
            self.assertNotIn("errors", content)
            self.assertTrue(content["data"]["tokenAuth"]["token"])

    def test_a_wrong_code_returns_the_code_and_no_codes(self):
        payload = self._confirm("000000")

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], INVALID_SECOND_FACTOR)
        self.assertIsNone(payload["codes"])
        self.assertFalse(devices.has_second_factor(self.user))

    def test_a_throttled_attempt_says_when_it_lifts(self):
        _throttle(self.device)

        payload = self._confirm(_code(self.device))

        self.assertEqual(payload["error"], SECOND_FACTOR_THROTTLED)
        self.assertIsNotNone(payload["lockedUntil"])

    def test_nothing_pending_is_told_to_enrol(self):
        TOTPDevice.objects.filter(user=self.user).delete()

        payload = self._confirm("000000")

        self.assertEqual(payload["error"], SECOND_FACTOR_ENROLMENT_REQUIRED)

    def test_a_user_with_a_device_is_refused(self):
        TOTPDevice.objects.create(user=self.user, name="phone", confirmed=True)

        payload = self._confirm(_code(self.device))

        self.assertEqual(payload["error"], SECOND_FACTOR_ALREADY_ENROLLED)
        self.assertIsNone(payload["codes"])

    def test_the_codes_reach_no_mutation_log(self):
        before = MutationLog.objects.count()

        self._confirm(_code(self.device))

        self.assertEqual(MutationLog.objects.count(), before)


class EnrolmentGateTest(TestCase):
    """A user the policy leaves free already logs in on the password, so the
    password alone must not also bind an authenticator to them: whoever stole
    it would lock the owner out, and a password reset removes no device."""

    def setUp(self):
        self.password = _password()
        self.user = create_test_interactive_user(
            username="enrolGate", password=self.password, roles=[]
        )
        self.other = create_test_interactive_user(
            username="enrolGateOther", password=_password(), roles=[]
        )

    def _as(self, who):
        request = _request()
        request.user = who
        return request

    def _begin(self, request):
        return enrolment.begin(request, self.user.username, self.password)

    def test_without_their_login_a_free_user_is_refused_and_nothing_is_made(self):
        with _policy(policy.OPTIONAL), self.assertRaises(SecondFactorError) as raised:
            self._begin(_request())

        self.assertEqual(raised.exception.code, SECOND_FACTOR_LOGIN_REQUIRED)
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())

    def test_signed_in_as_themselves_a_free_user_enrols(self):
        with _policy(policy.OPTIONAL):
            device = self._begin(self._as(self.user))

        self.assertFalse(device.confirmed)

    def test_signed_in_as_someone_else_is_refused(self):
        with _policy(policy.OPTIONAL), self.assertRaises(SecondFactorError) as raised:
            self._begin(self._as(self.other))

        self.assertEqual(raised.exception.code, SECOND_FACTOR_LOGIN_REQUIRED)

    def test_completing_needs_the_login_too(self):
        with _policy(policy.OPTIONAL):
            device = self._begin(self._as(self.user))
            with self.assertRaises(SecondFactorError) as raised:
                enrolment.complete(
                    _request(), self.user.username, self.password, _code(device)
                )
            self.assertEqual(raised.exception.code, SECOND_FACTOR_LOGIN_REQUIRED)
            device.refresh_from_db()
            self.assertFalse(device.confirmed)

            codes = enrolment.complete(
                self._as(self.user), self.user.username, self.password, _code(device)
            )

        self.assertEqual(len(codes), 10)

    def test_a_user_outside_the_named_roles_is_free(self):
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            with self.assertRaises(SecondFactorError) as raised:
                self._begin(_request())

        self.assertEqual(raised.exception.code, SECOND_FACTOR_LOGIN_REQUIRED)

    def test_a_bound_user_needs_no_login(self):
        with _policy(policy.MANDATORY):
            device = self._begin(_request())

        self.assertFalse(device.confirmed)


class EnrolmentGateMutationTest(openIMISGraphQLTestCase):
    """The GraphQL surface of the gate: the frontend's profile page sends the
    user's token, the public enrolment page does not."""

    def setUp(self):
        super().setUp()
        self.password = _password()
        self.user = create_test_interactive_user(
            username="enrolGateGql", password=self.password, roles=[]
        )

    def _enrol(self, **headers):
        response = self.query(
            ENROL,
            variables={"username": self.user.username, "password": self.password},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)["data"]["enrolSecondFactor"]

    def test_a_free_user_without_a_token_is_told_to_log_in(self):
        with _policy(policy.OPTIONAL):
            result = self._enrol()

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], SECOND_FACTOR_LOGIN_REQUIRED)
        self.assertIsNone(result["totp"])

    def test_a_free_user_with_their_own_token_gets_the_secret(self):
        token = BaseTestContext(user=self.user).get_jwt()

        with _policy(policy.OPTIONAL):
            result = self._enrol(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertTrue(result["success"])
        self.assertTrue(result["totp"]["secret"])
