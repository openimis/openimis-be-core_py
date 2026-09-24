import base64
import json
from secrets import token_hex
from unittest.mock import patch

from axes.models import AccessAttempt
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import DatabaseError
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import RequestFactory, TestCase
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.exceptions import AuthenticationFailed

from core.apps import CoreConfig
from core.auth import devices, policy
from core.auth.basic import SecondFactorBasicAuthentication
from core.auth.login import (
    SECOND_FACTOR_ENROLMENT_REQUIRED,
    SECOND_FACTOR_REQUIRED,
    SecondFactorError,
    authenticate_login,
    mfa_required,
)
from core.models import ModuleConfiguration
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.services import create_or_update_user_roles
from core.test_helpers import (
    create_test_interactive_user,
    create_test_role,
    create_test_technical_user,
)
from core.tests.test_second_factor import _code


def _policy(mode, roles=()):
    """Set the two policy attributes for one test - the same class attributes
    CoreConfig.ready() sets from the module configuration."""
    return patch.multiple(
        CoreConfig,
        second_factor_policy=mode,
        second_factor_mandatory_roles=list(roles),
    )


def _password():
    """Generated, so no password-shaped literal ends up in the repository."""
    return token_hex(16) + "Aa1!"


def _request():
    """A request with a real, empty session - what open_admin_session needs."""
    request = RequestFactory().post("/api/graphql")
    SessionMiddleware(lambda r: None).process_request(request)
    return request


def _basic_request(username, password):
    """A GET carrying an HTTP Basic header, as a REST client would send it."""
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return RequestFactory().get(
        "/api/api_fhir_r4/Patient/", HTTP_AUTHORIZATION=f"Basic {encoded}"
    )


def _enrol(user):
    """A confirmed TOTP device, with the replay floor rewound.

    Confirming consumes the time step whose code was used; rewind rather than
    make every test wait 30 seconds. The property itself is pinned by
    test_second_factor.test_the_code_that_confirmed_cannot_also_log_in.
    """
    device = devices.enrol_totp(user)
    assert devices.confirm_totp(device, _code(device))
    TOTPDevice.objects.filter(pk=device.pk).update(last_t=-1)
    device.refresh_from_db()
    return device


def _failures(username):
    attempt = AccessAttempt.objects.filter(username=username).first()
    return attempt.failures_since_start if attempt else 0


class PolicyMandatesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supervisor_role = create_test_role(name="Supervisor")
        cls.agent_role = create_test_role(name="Field Agent")
        # Explicit roles throughout: the helper's default is the IMIS
        # Administrator role plus is_superuser, which per_role binds by itself.
        cls.supervisor = create_test_interactive_user(
            username="policySupervisor", roles=[cls.supervisor_role.id]
        )
        cls.agent = create_test_interactive_user(
            username="policyAgent", roles=[cls.agent_role.id]
        )
        cls.superuser = create_test_interactive_user(
            username="policySuper",
            roles=[cls.agent_role.id],
            custom_props={"is_superuser": True},
        )
        cls.technical = create_test_technical_user(username="policyTech")
        # is_staff is what AdminSite.has_permission gates on, and the admin
        # form sets it from is_superuser, so this is the shape a technical
        # account created through the admin actually has.
        cls.staff_technical = create_test_technical_user(
            username="policyTechStaff", staff=True, super_user=True
        )

    def test_optional_binds_nobody(self):
        with _policy(policy.OPTIONAL):
            for user in (
                self.supervisor,
                self.agent,
                self.superuser,
                self.technical,
                self.staff_technical,
            ):
                with self.subTest(user=user.username):
                    self.assertFalse(policy.mandates(user))

    def test_mandatory_binds_every_interactive_user(self):
        with _policy(policy.MANDATORY):
            self.assertTrue(policy.mandates(self.supervisor))
            self.assertTrue(policy.mandates(self.agent))
            self.assertTrue(policy.mandates(self.superuser))

    def test_a_plain_technical_user_is_never_bound(self):
        # No admin, no rights of its own, nothing but the API - and the reason
        # HTTP Basic stays enabled at all.
        self.assertFalse(self.technical.is_staff)
        for mode in policy.POLICIES:
            with self.subTest(mode=mode), _policy(mode, ["Supervisor"]):
                self.assertFalse(policy.mandates(self.technical))

    def test_a_staff_technical_user_is_bound(self):
        # It reaches the Django admin (AdminSite.has_permission is is_active
        # and is_staff; User.is_staff delegates to TechnicalUser.is_staff), and
        # open_admin_session opens that session for any is_staff user. An
        # account that can administer the deployment on a password alone is
        # what the policy is for, whichever table it lives in.
        self.assertTrue(self.staff_technical.is_staff)
        for mode in (policy.PER_ROLE, policy.MANDATORY):
            with self.subTest(mode=mode), _policy(mode, ["Supervisor"]):
                self.assertTrue(policy.mandates(self.staff_technical))

    def test_per_role_binds_the_named_roles_only(self):
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            self.assertTrue(policy.mandates(self.supervisor))
            self.assertFalse(policy.mandates(self.agent))

    def test_per_role_binds_a_superuser_whatever_their_roles(self):
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            self.assertTrue(policy.mandates(self.superuser))

    def test_the_superuser_flag_binds_on_its_own(self):
        # is_imis_admin covers the flag today, but InteractiveUser.is_imis_admin
        # is marked deprecated upstream. If it is removed or narrowed, a
        # superuser must still be bound - a predicate that failed open here
        # would silently exempt the strongest account in the deployment.
        with _policy(policy.PER_ROLE, ["Supervisor"]), patch.object(
            type(self.superuser), "is_imis_admin", property(lambda self: False)
        ):
            self.assertTrue(self.superuser.is_superuser)
            self.assertTrue(policy.mandates(self.superuser))

    def test_the_technical_rows_own_superuser_flag_does_not_bind(self):
        # It escalates nothing: core_User has its own is_superuser column and
        # nothing syncs them, which test_technical_user_auth pins. Refusing an
        # integration over an inert flag would be a break for nothing; where it
        # matters the admin form sets is_staff alongside it.
        inert = create_test_technical_user(
            username="policyTechInert", super_user=True, staff=False
        )
        self.assertTrue(inert.t_user.is_superuser)
        self.assertFalse(inert.is_superuser)
        with _policy(policy.MANDATORY):
            self.assertFalse(policy.mandates(inert))

    def test_per_role_with_no_roles_named_still_binds_the_privileged(self):
        with _policy(policy.PER_ROLE, []):
            self.assertTrue(policy.mandates(self.superuser))
            self.assertFalse(policy.mandates(self.agent))

    def test_a_closed_role_assignment_no_longer_binds(self):
        # Moving the user off the role closes the UserRole row (validity_to);
        # the mandate must read validity the way every right check does.
        user = create_test_interactive_user(
            username="policyMoved", roles=[self.supervisor_role.id]
        )
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            self.assertTrue(policy.mandates(user))
            create_or_update_user_roles(user.i_user, [self.agent_role.id], None)
            self.assertFalse(policy.mandates(user))

    def test_a_name_matching_no_role_binds_nobody(self):
        # The validator refuses such a name at save time; here the predicate
        # must simply not match it, and must not raise.
        with _policy(policy.PER_ROLE, ["No Such Role"]):
            self.assertFalse(policy.mandates(self.agent))

    def test_an_unknown_policy_value_is_refused_not_guessed(self):
        # Neither fail-open (optional) nor fail-closed (mandatory) is right
        # for a typo; the login must fail loudly until the row is fixed.
        with _policy("sometimes"), self.assertRaises(ImproperlyConfigured):
            policy.mandates(self.agent)


class PolicyConfigureTest(TestCase):
    def test_configure_applies_both_keys(self):
        with _policy(policy.OPTIONAL):
            policy.configure(
                {
                    "second_factor_policy": "per_role",
                    "second_factor_mandatory_roles": ["Supervisor"],
                }
            )
            self.assertEqual(CoreConfig.second_factor_policy, "per_role")
            self.assertEqual(CoreConfig.second_factor_mandatory_roles, ["Supervisor"])

    def test_configure_tolerates_a_null_role_list(self):
        with _policy(policy.OPTIONAL):
            policy.configure(
                {
                    "second_factor_policy": "optional",
                    "second_factor_mandatory_roles": None,
                }
            )
            self.assertEqual(CoreConfig.second_factor_mandatory_roles, [])


class MfaRequiredTest(TestCase):
    """The one predicate: enrolment binds under every policy; the policy binds
    more."""

    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.role = create_test_role(name="Supervisor")
        cls.other = create_test_role(name="Field Agent")
        cls.bound = create_test_interactive_user(
            username="mfaBound", password=cls.password, roles=[cls.role.id]
        )
        cls.free = create_test_interactive_user(
            username="mfaFree", password=cls.password, roles=[cls.other.id]
        )

    def test_an_enrolled_user_is_required_under_every_policy(self):
        _enrol(self.free)
        for mode in policy.POLICIES:
            with self.subTest(mode=mode), _policy(mode, ["Supervisor"]):
                self.assertTrue(mfa_required(self.free))

    def test_an_unenrolled_user_is_required_only_when_the_policy_binds_them(self):
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            self.assertTrue(mfa_required(self.bound))
            self.assertFalse(mfa_required(self.free))


class MandatedLoginTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.role = create_test_role(name="Supervisor")
        cls.other = create_test_role(name="Field Agent")
        cls.bound = create_test_interactive_user(
            username="loginBound", password=cls.password, roles=[cls.role.id]
        )
        cls.free = create_test_interactive_user(
            username="loginFree", password=cls.password, roles=[cls.other.id]
        )

    def test_a_bound_user_with_no_device_is_told_to_enrol(self):
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            with self.assertRaises(SecondFactorError) as raised:
                authenticate_login(_request(), "loginBound", self.password)
        self.assertEqual(raised.exception.code, SECOND_FACTOR_ENROLMENT_REQUIRED)
        self.assertEqual(
            raised.exception.extensions, {"code": SECOND_FACTOR_ENROLMENT_REQUIRED}
        )

    def test_a_stray_code_does_not_turn_enrol_into_invalid(self):
        # The device check precedes the otp branch: the answer is "enrol",
        # and INVALID_SECOND_FACTOR would send the frontend to a code field.
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            with self.assertRaises(SecondFactorError) as raised:
                authenticate_login(
                    _request(), "loginBound", self.password, otp="123456"
                )
        self.assertEqual(raised.exception.code, SECOND_FACTOR_ENROLMENT_REQUIRED)

    def test_being_told_to_enrol_is_not_a_failed_login(self):
        # Only a rejected code counts against the lockout; being asked for a
        # factor is not guessing.
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            with self.assertRaises(SecondFactorError):
                authenticate_login(_request(), "loginBound", self.password)
        self.assertEqual(_failures("loginBound"), 0)

    def test_a_bound_user_who_enrolled_is_asked_for_the_code_then_logs_in(self):
        device = _enrol(self.bound)
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            with self.assertRaises(SecondFactorError) as raised:
                authenticate_login(_request(), "loginBound", self.password)
            self.assertEqual(raised.exception.code, SECOND_FACTOR_REQUIRED)
            user = authenticate_login(
                _request(), "loginBound", self.password, otp=_code(device)
            )
        self.assertEqual(user.pk, self.bound.pk)

    def test_a_user_the_policy_leaves_alone_logs_in_on_the_password(self):
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            user = authenticate_login(_request(), "loginFree", self.password)
        self.assertEqual(user.pk, self.free.pk)

    def test_a_wrong_password_still_fails_first(self):
        # Nothing about the policy may be learned without the password.
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            with self.assertRaises(AuthenticationFailed):
                authenticate_login(_request(), "loginBound", "not-it")

    def test_mandatory_binds_the_unenrolled_field_agent_too(self):
        with _policy(policy.MANDATORY):
            with self.assertRaises(SecondFactorError) as raised:
                authenticate_login(_request(), "loginFree", self.password)
        self.assertEqual(raised.exception.code, SECOND_FACTOR_ENROLMENT_REQUIRED)

    def test_mandatory_still_logs_a_plain_technical_user_in(self):
        technical = create_test_technical_user(
            username="loginTech", password=self.password
        )
        with _policy(policy.MANDATORY):
            user = authenticate_login(_request(), "loginTech", self.password)
        self.assertEqual(user.pk, technical.pk)

    def test_a_staff_technical_user_is_told_to_enrol(self):
        # It can log in here and, being is_staff, open_admin_session gives it
        # the Django admin. Exempting it would leave an admin-capable
        # password-only login outside the policy.
        create_test_technical_user(
            username="loginTechStaff",
            password=self.password,
            staff=True,
            super_user=True,
        )
        with _policy(policy.MANDATORY):
            with self.assertRaises(SecondFactorError) as raised:
                authenticate_login(_request(), "loginTechStaff", self.password)
        self.assertEqual(raised.exception.code, SECOND_FACTOR_ENROLMENT_REQUIRED)


class BasicUnderPolicyTest(TestCase):
    """The HTTP Basic authenticator asks the same predicate; these pin what the
    policy does to it, the technical accounts included."""

    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.role = create_test_role(name="Supervisor")
        cls.other = create_test_role(name="Field Agent")
        cls.bound = create_test_interactive_user(
            username="basicBound", password=cls.password, roles=[cls.role.id]
        )
        cls.free = create_test_interactive_user(
            username="basicFree", password=cls.password, roles=[cls.other.id]
        )
        cls.technical = create_test_technical_user(
            username="basicTech", password=cls.password
        )
        cls.staff_technical = create_test_technical_user(
            username="basicTechStaff",
            password=cls.password,
            staff=True,
            super_user=True,
        )

    def test_basic_refuses_a_bound_user_with_no_device(self):
        # The header cannot carry a code and cannot enrol; the same code as
        # for an enrolled user, since the remedy - the token flow - is the same.
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            with self.assertRaises(AuthenticationFailed) as caught:
                SecondFactorBasicAuthentication().authenticate(
                    _basic_request("basicBound", self.password)
                )
        self.assertEqual(str(caught.exception.detail), SECOND_FACTOR_REQUIRED)

    def test_basic_admits_a_user_the_policy_leaves_alone(self):
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            user, _auth = SecondFactorBasicAuthentication().authenticate(
                _basic_request("basicFree", self.password)
            )
        self.assertEqual(user.pk, self.free.pk)

    def test_basic_still_admits_a_plain_technical_user_under_mandatory(self):
        # The integrations HTTP Basic exists for are untouched by any of this,
        # under the strictest policy there is.
        with _policy(policy.MANDATORY):
            user, _auth = SecondFactorBasicAuthentication().authenticate(
                _basic_request("basicTech", self.password)
            )
        self.assertEqual(user.username, "basicTech")

    def test_basic_refuses_a_staff_technical_user_under_mandatory(self):
        # The deliberate cost of not exempting it: an integration whose account
        # was made staff stops working over Basic when a policy binds it.
        with _policy(policy.MANDATORY):
            with self.assertRaises(AuthenticationFailed) as caught:
                SecondFactorBasicAuthentication().authenticate(
                    _basic_request("basicTechStaff", self.password)
                )
        self.assertEqual(str(caught.exception.detail), SECOND_FACTOR_REQUIRED)


TOKEN_AUTH = """
    mutation login($username: String!, $password: String!, $otp: String) {
        tokenAuth(username: $username, password: $password, otp: $otp) { token }
    }
"""


class TokenAuthEnrolmentRequiredTest(openIMISGraphQLTestCase):
    """The fourth code reaches the client the way the other three do: HTTP 200,
    errors[0].message, repeated in extensions.code."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = _password()
        cls.role = create_test_role(name="Supervisor")
        cls.user = create_test_interactive_user(
            username="tokenAuthBound", password=cls.password, roles=[cls.role.id]
        )

    def test_a_bound_unenrolled_user_is_told_to_enrol(self):
        with _policy(policy.PER_ROLE, ["Supervisor"]):
            response = self.query(
                TOKEN_AUTH,
                variables={"username": "tokenAuthBound", "password": self.password},
            )
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content)
        self.assertEqual(
            content["errors"][0]["message"], SECOND_FACTOR_ENROLMENT_REQUIRED
        )
        self.assertEqual(
            content["errors"][0]["extensions"]["code"], SECOND_FACTOR_ENROLMENT_REQUIRED
        )
        self.assertIsNone(content["data"]["tokenAuth"])


def _row(**cfg):
    return ModuleConfiguration(
        module="core", layer="be", version="1", config=json.dumps(cfg)
    )


class PolicyConfigurationValidationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_test_role(name="Supervisor")

    def test_a_row_naming_neither_key_is_fine(self):
        # Every other core key is optional in the row; these two are too.
        _row(csrf_protect_login=False).clean()

    def test_a_valid_policy_is_accepted(self):
        _row(
            second_factor_policy="per_role",
            second_factor_mandatory_roles=["Supervisor"],
        ).clean()

    def test_an_unknown_policy_value_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            _row(second_factor_policy="sometimes").clean()
        self.assertIn("config", caught.exception.message_dict)

    def test_roles_must_be_a_list_of_strings(self):
        for bad in ("Supervisor", [1, 2], {"name": "Supervisor"}):
            with self.subTest(value=bad), self.assertRaises(ValidationError):
                _row(second_factor_mandatory_roles=bad).clean()

    def test_a_config_body_that_is_not_an_object_is_refused(self):
        # clean() guards JSON syntax but not shape, so a valid-JSON list
        # reaches this validator. It must answer with the field error the
        # model's contract promises, not an AttributeError out of save().
        row = ModuleConfiguration(
            module="core", layer="be", version="1", config="[1, 2]"
        )
        with self.assertRaises(ValidationError) as caught:
            row.clean()
        self.assertIn("config", caught.exception.message_dict)

    def test_a_name_matching_no_valid_role_is_refused(self):
        # Fail closed here rather than open at login: a misspelt name would
        # otherwise silently exempt everyone who holds the real one.
        with self.assertRaises(ValidationError) as caught:
            _row(second_factor_mandatory_roles=["Supervisor", "Suprevisor"]).clean()
        self.assertIn("Suprevisor", str(caught.exception))


class PolicyConfigurationReloadTest(TestCase):
    def test_saving_the_row_applies_the_policy_without_a_restart(self):
        create_test_role(name="Supervisor")
        with _policy(policy.OPTIONAL):
            with self.captureOnCommitCallbacks(execute=True):
                _row(
                    second_factor_policy="per_role",
                    second_factor_mandatory_roles=["Supervisor"],
                ).save()
            self.assertEqual(CoreConfig.second_factor_policy, "per_role")
            self.assertEqual(CoreConfig.second_factor_mandatory_roles, ["Supervisor"])


class PolicyLoadTest(TestCase):
    """The policy is read at start straight from the row, and a read that
    fails leaves it unknown and refuses logins rather than defaulting to
    "optional" - everyone exempt."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(
            username="policyLoad", password=_password(), roles=[]
        )

    def test_a_failed_read_leaves_the_policy_unknown_not_optional(self):
        with _policy(policy.OPTIONAL):
            with patch.object(policy, "_read", side_effect=DatabaseError("down")):
                policy.load()
            self.assertIsNone(CoreConfig.second_factor_policy)

    def test_logins_are_refused_while_the_row_cannot_be_read(self):
        with _policy(None):
            with patch.object(policy, "_read", side_effect=DatabaseError("down")):
                with self.assertRaises(ImproperlyConfigured):
                    policy.mandates(self.user)

    def test_the_first_login_after_the_row_becomes_readable_loads_it(self):
        ModuleConfiguration.objects.bulk_create(
            [_row(second_factor_policy="mandatory")]
        )
        with _policy(None):
            self.assertTrue(policy.mandates(self.user))
            self.assertEqual(CoreConfig.second_factor_policy, policy.MANDATORY)

    def test_load_applies_the_row(self):
        ModuleConfiguration.objects.bulk_create(
            [
                _row(
                    second_factor_policy="per_role",
                    second_factor_mandatory_roles=["Supervisor"],
                )
            ]
        )
        with _policy(policy.OPTIONAL):
            policy.load()
            self.assertEqual(CoreConfig.second_factor_policy, policy.PER_ROLE)
            self.assertEqual(CoreConfig.second_factor_mandatory_roles, ["Supervisor"])
