from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from core.apps import CoreConfig
from core.auth import policy
from core.services import create_or_update_user_roles
from core.test_helpers import (
    create_test_interactive_user,
    create_test_role,
    create_test_technical_user,
)


def _policy(mode, roles=()):
    """Set the two policy attributes for one test - the same class attributes
    CoreConfig.ready() sets from the module configuration."""
    return patch.multiple(
        CoreConfig,
        second_factor_policy=mode,
        second_factor_mandatory_roles=list(roles),
    )


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
