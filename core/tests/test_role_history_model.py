from django.test import TestCase

from core.models import Role, RoleRight, UserRole


class RoleHistoryModelTest(TestCase):
    def _role(self, name="Auditors"):
        return Role.objects.create(
            name=name, is_system=0, is_blocked=False, audit_user_id=1
        )

    def test_legacy_columns_are_preserved(self):
        self.assertEqual(Role._meta.get_field("id").db_column, "RoleID")
        self.assertEqual(Role._meta.get_field("uuid").db_column, "RoleUUID")
        self.assertEqual(Role._meta.get_field("legacy_id").db_column, "LegacyID")
        self.assertEqual(RoleRight._meta.get_field("id").db_column, "RoleRightID")
        self.assertEqual(RoleRight._meta.get_field("role").db_column, "RoleID")
        self.assertEqual(UserRole._meta.get_field("id").db_column, "UserRoleID")

    def test_creating_a_role_records_a_creation_entry(self):
        role = self._role()
        self.assertEqual(role.history.count(), 1)
        self.assertEqual(role.history.first().history_type, "+")

    def test_updating_a_role_records_a_second_version(self):
        role = self._role()
        role.name = "Auditors QA"
        role.save()
        self.assertEqual(role.history.count(), 2)
        self.assertEqual(role.history.first().history_type, "~")

    def test_diff_against_reports_the_changed_attribute(self):
        role = self._role()
        role.name = "Auditors QA"
        role.save()
        newest, previous = role.history.all()[0], role.history.all()[1]
        changed = [c.field for c in newest.diff_against(previous).changes]
        self.assertIn("name", changed)

    def test_rights_are_versioned_per_grant(self):
        role = self._role()
        right = RoleRight.objects.create(role=role, right_id=121701, audit_user_id=1)
        right.active = False
        right.save()
        self.assertEqual([h.history_type for h in right.history.all()], ["~", "+"])
