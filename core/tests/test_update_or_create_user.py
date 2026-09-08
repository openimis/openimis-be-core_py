from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import Language, Role, User
from core.schema import update_or_create_user
from core.test_helpers import create_test_interactive_user, create_test_role
from core.user_types import UT_INTERACTIVE


class DuplicateSystemRoleUserTest(TestCase):
    def setUp(self):
        Language.objects.get_or_create(
            code="en",
            defaults={"name": "English", "sort_order": 1},
        )
        self.admin = create_test_interactive_user(username="sysroleadmin")
        self.admin_role = Role.objects.filter(
            is_system=Role.IMIS_ADMINISTRATOR, *Role.filter_validity()
        ).first()
        if self.admin_role is None:
            self.admin_role = create_test_role(
                [], name="IMIS Administrator", is_system=Role.IMIS_ADMINISTRATOR
            )
        self.duplicate_admin_role = Role.objects.create(
            name="IMIS Administrator Duplicate",
            is_system=Role.IMIS_ADMINISTRATOR,
            is_blocked=False,
            audit_user_id=-1,
        )

    def test_get_system_role_ids_returns_all_duplicates(self):
        ids = Role.get_system_role_ids(Role.IMIS_ADMINISTRATOR)
        self.assertGreaterEqual(len(ids), 2)
        self.assertIn(self.admin_role.id, ids)
        self.assertIn(self.duplicate_admin_role.id, ids)

    def test_create_user_with_duplicate_imis_admin_roles(self):
        other_role = create_test_role([], name="ClerkRole")
        created = update_or_create_user(
            {
                "username": "duproleu1",
                "last_name": "Last",
                "other_names": "Other",
                "email": "duproleu1@example.com",
                "language": "en",
                "roles": [other_role.id],
                "user_types": [UT_INTERACTIVE],
            },
            self.admin,
        )
        self.assertIsNotNone(created)
        self.assertEqual(created.username, "duproleu1")
        self.assertTrue(User.objects.filter(username="duproleu1").exists())

    def test_admin_can_keep_either_duplicate_admin_role(self):
        updated = update_or_create_user(
            {
                "uuid": str(self.admin.id),
                "username": self.admin.username,
                "last_name": self.admin.i_user.last_name,
                "other_names": self.admin.i_user.other_names,
                "email": "sysroleadmin@example.com",
                "language": "en",
                "roles": [self.duplicate_admin_role.id],
                "user_types": [UT_INTERACTIVE],
            },
            self.admin,
        )
        self.assertEqual(updated.id, self.admin.id)

    def test_admin_cannot_drop_all_admin_roles(self):
        clerk = create_test_role([], name="ClerkRoleNoAdmin")
        with self.assertRaises(ValidationError) as cm:
            update_or_create_user(
                {
                    "uuid": str(self.admin.id),
                    "username": self.admin.username,
                    "last_name": self.admin.i_user.last_name,
                    "other_names": self.admin.i_user.other_names,
                    "email": "sysroleadmin@example.com",
                    "language": "en",
                    "roles": [clerk.id],
                    "user_types": [UT_INTERACTIVE],
                },
                self.admin,
            )
        self.assertIn("cannot deprovision", str(cm.exception))
