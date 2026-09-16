"""Getting back into an account whose second factor is lost.

Two ways, and the tests keep them unequal: a user who still holds a device
re-issues their own recovery codes, while a user who holds nothing needs an
administrator whose action is gated, recorded and ends every session.
"""

import json

from django.core.exceptions import ValidationError
from django.test import TestCase
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from graphql_jwt.refresh_token.shortcuts import create_refresh_token
from rest_framework.exceptions import AuthenticationFailed

from core.auth import devices, recovery, second_factor
from core.auth.login import (
    INVALID_SECOND_FACTOR,
    SECOND_FACTOR_ENROLMENT_REQUIRED,
    SECOND_FACTOR_REQUIRED,
    SECOND_FACTOR_THROTTLED,
    SecondFactorError,
)
from core.models import MutationLog, User, UserMutation
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import (
    create_test_interactive_user,
    create_test_role,
    create_test_technical_user,
)
from core.tests.test_auth_revocation import _now, _stored_not_before
from core.tests.test_login_flow import _enrol, _password, _throttle
from core.tests.test_second_factor import _code


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


class ResetUserSecondFactorMutationTest(openIMISGraphQLTestCase):
    """The GraphQL surface and the record it leaves behind."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = create_test_interactive_user(
            username="mfaResetAdmin", password=_password()
        )
        cls.nobody = create_test_interactive_user(
            username="mfaResetNobody", password=_password(), roles=[]
        )

    def setUp(self):
        super().setUp()
        self.target = create_test_interactive_user(
            username="mfaResetTarget", password=_password(), roles=[]
        )
        _enrol(self.target)

    def _reset(self, caller, target_id):
        """The mutation, returning its log row.

        follow=False: the base class records the outcome on the log rather
        than in the response, so a refusal has to be read there too and
        waiting for a success would hang on one.
        """
        token = BaseTestContext(user=caller).get_jwt()
        content = self.send_mutation(
            "resetUserSecondFactor",
            {"uuid": str(target_id)},
            token,
            follow=False,
            add_client_mutation_id=True,
        )
        return MutationLog.objects.get(
            id=content["data"]["resetUserSecondFactor"]["internalId"]
        )

    def test_an_administrator_resets_a_user_and_the_log_records_it(self):
        log = self._reset(self.admin, self.target.id)

        self.assertEqual(log.status, MutationLog.SUCCESS, log.error)
        self.assertEqual(log.user_id, self.admin.id)
        self.assertEqual(json.loads(log.json_content)["uuid"], str(self.target.id))
        self.assertTrue(
            UserMutation.objects.filter(core_user=self.target, mutation=log).exists()
        )
        self.assertFalse(devices.has_second_factor(self.target))

    def test_a_refusal_is_recorded_too_and_changes_nothing(self):
        log = self._reset(self.nobody, self.target.id)

        self.assertEqual(log.status, MutationLog.ERROR)
        self.assertEqual(log.user_id, self.nobody.id)
        self.assertTrue(devices.has_second_factor(self.target))
        # The link is written while the mutation is validated, before anyone
        # is allowed through, so a refused attempt is traceable to the account
        # it was aimed at rather than only to the caller.
        self.assertTrue(
            UserMutation.objects.filter(core_user=self.target, mutation=log).exists()
        )

    def test_a_uuid_that_is_nobody_fails_before_the_service_runs(self):
        log = self._reset(self.admin, "00000000-0000-0000-0000-000000000000")

        self.assertEqual(log.status, MutationLog.ERROR)
        self.assertTrue(devices.has_second_factor(self.target))

    def test_an_anonymous_caller_is_refused(self):
        response = self.query(
            """
            mutation {
                resetUserSecondFactor(input: {uuid: "%s", clientMutationId: "anon"}) {
                    internalId
                }
            }
            """
            % self.target.id
        )

        content = json.loads(response.content)
        log = MutationLog.objects.get(
            id=content["data"]["resetUserSecondFactor"]["internalId"]
        )
        self.assertEqual(log.status, MutationLog.ERROR)
        self.assertIsNone(log.user_id)
        self.assertTrue(devices.has_second_factor(self.target))


class ReissueRecoveryCodesTest(TestCase):
    """The service: who gets a new set, and what it costs them."""

    def setUp(self):
        self.user = create_test_interactive_user(
            username="mfaReissue", password=_password(), roles=[]
        )

    def test_a_user_with_no_device_is_told_to_enrol(self):
        with self.assertRaises(SecondFactorError) as raised:
            recovery.reissue_recovery_codes(self.user, "000000")

        self.assertEqual(raised.exception.code, SECOND_FACTOR_ENROLMENT_REQUIRED)
        self.assertEqual(_codes_stored(self.user), set())

    def test_an_authenticator_code_replaces_the_set(self):
        device = _enrol(self.user)
        old = set(devices.issue_recovery_codes(self.user))

        new = recovery.reissue_recovery_codes(self.user, _code(device))

        self.assertEqual(len(new), 10)
        self.assertEqual(_codes_stored(self.user), set(new))
        self.assertTrue(old.isdisjoint(new))

    def test_a_wrong_code_is_invalid_and_leaves_the_old_set(self):
        _enrol(self.user)
        old = set(devices.issue_recovery_codes(self.user))

        with self.assertRaises(SecondFactorError) as raised:
            recovery.reissue_recovery_codes(self.user, "000000")

        self.assertEqual(raised.exception.code, INVALID_SECOND_FACTOR)
        self.assertEqual(_codes_stored(self.user), old)

    def test_a_recovery_code_can_refill_the_set_and_is_spent_doing_it(self):
        _enrol(self.user)
        old = devices.issue_recovery_codes(self.user)

        new = recovery.reissue_recovery_codes(self.user, old[0])

        self.assertEqual(len(new), 10)
        self.assertNotIn(old[0], _codes_stored(self.user))

    def test_a_new_code_logs_in_once(self):
        device = _enrol(self.user)

        new = recovery.reissue_recovery_codes(self.user, _code(device))

        self.assertTrue(second_factor.verify(self.user, new[0]).ok)
        self.assertEqual(
            second_factor.verify(self.user, new[0]).outcome, second_factor.INVALID
        )

    def test_an_empty_code_asks_for_one_without_charging_the_devices(self):
        device = _enrol(self.user)
        devices.issue_recovery_codes(self.user)

        with self.assertRaises(SecondFactorError) as raised:
            recovery.reissue_recovery_codes(self.user, "")

        self.assertEqual(raised.exception.code, SECOND_FACTOR_REQUIRED)
        device.refresh_from_db()
        self.assertEqual(device.throttling_failure_count, 0)

    def test_a_throttled_device_reports_when_it_lifts(self):
        device = _enrol(self.user)
        devices.issue_recovery_codes(self.user)
        _throttle(device)
        _throttle(StaticDevice.objects.get(user=self.user))

        with self.assertRaises(SecondFactorError) as raised:
            recovery.reissue_recovery_codes(self.user, _code(device))

        self.assertEqual(raised.exception.code, SECOND_FACTOR_THROTTLED)
        self.assertIsNotNone(raised.exception.extensions["lockedUntil"])


class IssueRecoveryCodesMutationTest(openIMISGraphQLTestCase):
    """The GraphQL surface: the codes come back once, and nowhere else."""

    ISSUE = """
        mutation {
            issueRecoveryCodes(input: {otp: "%s", clientMutationId: "reissue"}) {
                codes
                success
                error
            }
        }
    """

    def setUp(self):
        super().setUp()
        self.user = create_test_interactive_user(
            username="mfaIssueCodes", password=_password(), roles=[]
        )
        self.device = _enrol(self.user)
        self.token = BaseTestContext(user=self.user).get_jwt()

    def _issue(self, otp, token=None):
        response = self.query(
            self.ISSUE % otp,
            headers={"HTTP_AUTHORIZATION": f"Bearer {token or self.token}"},
        )
        return json.loads(response.content)

    def test_a_current_code_returns_a_fresh_set(self):
        body = self._issue(_code(self.device))

        payload = body["data"]["issueRecoveryCodes"]
        self.assertTrue(payload["success"], payload["error"])
        self.assertEqual(len(payload["codes"]), 10)
        self.assertEqual(_codes_stored(self.user), set(payload["codes"]))

    def test_a_wrong_code_returns_the_code_not_codes(self):
        body = self._issue("000000")

        payload = body["data"]["issueRecoveryCodes"]
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], INVALID_SECOND_FACTOR)
        self.assertIsNone(payload["codes"])

    def test_the_codes_reach_no_mutation_log(self):
        before = MutationLog.objects.count()

        self._issue(_code(self.device))

        self.assertEqual(MutationLog.objects.count(), before)

    def test_an_anonymous_caller_is_refused(self):
        response = self.query(self.ISSUE % "000000")

        body = json.loads(response.content)
        payload = (body.get("data") or {}).get("issueRecoveryCodes")
        refused = "errors" in body or (payload and payload["success"] is False)
        self.assertTrue(refused, body)
        self.assertEqual(_codes_stored(self.user), set())
