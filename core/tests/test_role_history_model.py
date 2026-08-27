from django.test import TestCase

from core.datetimes.ne_datetime import NeDatetime
from core.models import Role, RoleRight, UserRole
from core.schema import update_or_create_role
from core.test_helpers import create_test_interactive_user


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

    def test_a_calendar_aware_datetime_is_accepted(self):
        # DirtyFieldsMixin, which the history model brings in, runs to_python()
        # on every field at construction. NeDatetime is not a datetime
        # subclass, so it has to be normalised before it reaches the model.
        user = create_test_interactive_user(username="RoleHistoryNeCalendar")
        role = update_or_create_role(
            {
                "name": "NepaliCalendarRole",
                "is_system": 0,
                "is_blocked": False,
                "audit_user_id": user.i_user.id,
                "validity_from": NeDatetime.now(),
            },
            user,
        )
        self.assertIsNotNone(role.id)
        self.assertEqual(role.history.count(), 1)
