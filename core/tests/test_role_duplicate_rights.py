import datetime
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from core.models import Role, RoleRight
from core.schema import duplicate_role, update_or_create_role
from core.test_helpers import create_test_interactive_user

_RIGHT_A = 121901
_RIGHT_B = 121902


class DuplicateRoleRightsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = create_test_interactive_user(username="DuplicateRoleTest")
        self.role = update_or_create_role(
            {
                "name": "DuplicateSourceRole",
                "is_system": 0,
                "is_blocked": False,
                "audit_user_id": self.user.i_user.id,
                "validity_from": datetime.datetime.now(),
                "rights_id": [_RIGHT_A, _RIGHT_B],
            },
            self.user,
        )
        # revoke B, so the source has one open and one closed right
        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A]}, self.user
        )

    def _open_rights(self, role):
        return set(
            RoleRight.objects.filter(
                role_id=role.id, validity_to__isnull=True
            ).values_list("right_id", flat=True)
        )

    def test_duplicate_does_not_inherit_revoked_rights(self):
        duplicate = duplicate_role(
            {"uuid": self.role.uuid, "name": "DupNoRightsArg"}, self.user
        )

        self.assertEqual(self._open_rights(duplicate), {_RIGHT_A})

    def test_duplicate_creates_one_row_per_right(self):
        duplicate = duplicate_role(
            {"uuid": self.role.uuid, "name": "DupOneRowPerRight"}, self.user
        )

        self.assertEqual(
            RoleRight.objects.filter(
                role_id=duplicate.id, right_id=_RIGHT_A
            ).count(),
            1,
        )

    def test_duplicate_rights_are_not_backdated_before_the_duplicate(self):
        duplicate = duplicate_role(
            {
                "uuid": self.role.uuid,
                "name": "DupExplicitRights",
                "rights_id": [_RIGHT_A],
            },
            self.user,
        )

        # Both sides must be read back from the database. Comparing a stored
        # datetime against an in-memory one is order-dependent here:
        # NeDatetimeTestCase (core/datetimes/test_ne_datetime.py) switches the
        # global core.calendar to the Nepali one in setUp and never restores
        # it, so stored values come back as ne_datetime (year 2083) while
        # datetime.now() stays Gregorian (2026) — the same instant, but not
        # numerically comparable.
        stored_duplicate = Role.objects.get(id=duplicate.id)
        role_right = RoleRight.objects.get(role_id=duplicate.id, right_id=_RIGHT_A)
        self.assertGreaterEqual(
            role_right.validity_from, stored_duplicate.validity_from
        )

    def test_explicit_rights_cannot_resurrect_a_revoked_right(self):
        # _RIGHT_B is revoked on the source; naming it explicitly must not
        # bring it back on the duplicate.
        duplicate = duplicate_role(
            {
                "uuid": self.role.uuid,
                "name": "DupExplicitB",
                "rights_id": [_RIGHT_B],
            },
            self.user,
        )

        self.assertEqual(self._open_rights(duplicate), set())

    def test_explicit_rights_narrow_the_copy(self):
        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A, _RIGHT_B]}, self.user
        )

        duplicate = duplicate_role(
            {
                "uuid": self.role.uuid,
                "name": "DupExplicitA",
                "rights_id": [_RIGHT_A],
            },
            self.user,
        )

        self.assertEqual(self._open_rights(duplicate), {_RIGHT_A})

    def test_a_failed_duplicate_leaves_no_orphan_role(self):
        roles_before = Role.objects.filter(name="DupDoomed").count()

        with patch.object(RoleRight, "save", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                duplicate_role(
                    {"uuid": self.role.uuid, "name": "DupDoomed"}, self.user
                )

        self.assertEqual(Role.objects.filter(name="DupDoomed").count(), roles_before)
