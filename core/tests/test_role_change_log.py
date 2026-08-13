import datetime

from django.core.cache import cache
from django.test import TestCase

from core.models import Role
from core.schema import set_role_deleted, update_or_create_role
from core.services.roleChangeLog import get_role_change_log
from core.services.userServices import create_or_update_user_roles
from core.test_helpers import create_test_interactive_user

_RIGHT_A = 121901
_RIGHT_B = 121902


class RoleChangeLogTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = create_test_interactive_user(username="RoleChangeLogTest")
        self.role = update_or_create_role(
            {
                "name": "ChangeLogTestRole",
                "is_system": 0,
                "is_blocked": False,
                "audit_user_id": self.user.i_user.id,
                "validity_from": datetime.datetime.now(),
                "rights_id": [_RIGHT_A],
            },
            self.user,
        )

    def _of_type(self, change_type, role_uuid=None):
        return [
            e
            for e in get_role_change_log(role_uuid or self.role.uuid)
            if e.change_type == change_type
        ]

    def test_role_creation_is_reported(self):
        entries = self._of_type("ROLE_CREATED")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].new_value, "ChangeLogTestRole")

    def test_renaming_a_role_is_reported_with_old_and_new_value(self):
        update_or_create_role(
            {"uuid": self.role.uuid, "name": "RenamedRole"}, self.user
        )

        entries = [e for e in self._of_type("ATTRIBUTE_CHANGED") if e.field == "name"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].old_value, "ChangeLogTestRole")
        self.assertEqual(entries[0].new_value, "RenamedRole")

    def test_blocking_a_role_is_reported(self):
        update_or_create_role({"uuid": self.role.uuid, "is_blocked": True}, self.user)

        entries = [
            e for e in self._of_type("ATTRIBUTE_CHANGED") if e.field == "is_blocked"
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].old_value, "False")
        self.assertEqual(entries[0].new_value, "True")

    def test_granting_a_right_is_reported(self):
        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A, _RIGHT_B]}, self.user
        )

        granted = {e.new_value for e in self._of_type("RIGHT_GRANTED")}
        self.assertEqual(granted, {str(_RIGHT_A), str(_RIGHT_B)})

    def test_revoking_a_right_is_reported(self):
        update_or_create_role({"uuid": self.role.uuid, "rights_id": []}, self.user)

        entries = self._of_type("RIGHT_REVOKED")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].new_value, str(_RIGHT_A))

    def test_revocation_has_no_actor(self):
        # audit_user_id on a RoleRight row identifies the granter, so it must
        # not be reported as the person who revoked the right.
        update_or_create_role({"uuid": self.role.uuid, "rights_id": []}, self.user)

        self.assertIsNone(self._of_type("RIGHT_REVOKED")[0].audit_user_id)

    def test_grant_reports_the_granting_user(self):
        entries = self._of_type("RIGHT_GRANTED")

        self.assertEqual(entries[0].audit_user_id, self.user.i_user.id)

    def test_user_assignment_is_reported(self):
        assignee = create_test_interactive_user(username="RoleChangeLogAssignee")
        create_or_update_user_roles(
            assignee.i_user, [self.role.id], self.user.i_user.id
        )

        entries = self._of_type("USER_ASSIGNED")
        self.assertIn(assignee.i_user.login_name, {e.new_value for e in entries})

    def test_entries_are_ordered_newest_first(self):
        update_or_create_role({"uuid": self.role.uuid, "name": "Second"}, self.user)
        update_or_create_role({"uuid": self.role.uuid, "name": "Third"}, self.user)

        timestamps = [e.timestamp for e in get_role_change_log(self.role.uuid)]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_a_deleted_role_still_has_a_change_log(self):
        # set_role_deleted stamps validity_to on the live row, so a
        # validity-filtered lookup would make this unreachable.
        update_or_create_role({"uuid": self.role.uuid, "name": "Doomed"}, self.user)
        role = Role.objects.get(uuid=self.role.uuid)
        set_role_deleted(role)

        entries = get_role_change_log(self.role.uuid)
        self.assertTrue(any(e.change_type == "ATTRIBUTE_CHANGED" for e in entries))

    def test_unknown_role_uuid_raises(self):
        with self.assertRaises(Role.DoesNotExist):
            get_role_change_log("00000000-0000-0000-0000-000000000000")
