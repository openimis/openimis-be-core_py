import datetime
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from core.models import Role, RoleRight
from core.schema import update_or_create_role
from core.test_helpers import create_test_interactive_user

_RIGHT_A = 121901
_RIGHT_B = 121902
_RIGHT_C = 121903


class RoleRightsVersioningTest(TestCase):
    def setUp(self):
        # InteractiveUser.rights caches under rights_<id> with timeout=None and
        # bypasses USE_CACHE, so it is live even during tests.
        cache.clear()
        self.user = create_test_interactive_user(username="RoleVersioningTest")
        self.role = update_or_create_role(
            {
                "name": "VersioningTestRole",
                "is_system": 0,
                "is_blocked": False,
                "audit_user_id": self.user.i_user.id,
                "validity_from": datetime.datetime.now(),
                "rights_id": [_RIGHT_A, _RIGHT_B],
            },
            self.user,
        )

    def _rows(self, right_id):
        return RoleRight.objects.filter(
            role_id=self.role.id, right_id=right_id
        ).order_by("validity_from", "id")

    def _open_rows(self, right_id):
        return self._rows(right_id).filter(validity_to__isnull=True)

    def test_revoking_then_regranting_a_right_creates_two_rows(self):
        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A]}, self.user
        )
        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A, _RIGHT_B]}, self.user
        )

        rows = list(self._rows(_RIGHT_B))
        self.assertEqual(len(rows), 2)
        self.assertIsNotNone(rows[0].validity_to)
        self.assertIsNone(rows[1].validity_to)

    def test_unchanged_right_keeps_its_original_row(self):
        original = self._rows(_RIGHT_A).first()

        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A]}, self.user
        )

        rows = list(self._rows(_RIGHT_A))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, original.id)
        self.assertIsNone(rows[0].validity_to)

    def test_closed_rows_keep_their_original_close_timestamp(self):
        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A]}, self.user
        )
        closed_at = self._rows(_RIGHT_B).first().validity_to

        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A]}, self.user
        )

        self.assertEqual(self._rows(_RIGHT_B).first().validity_to, closed_at)

    def test_empty_rights_list_revokes_everything(self):
        update_or_create_role({"uuid": self.role.uuid, "rights_id": []}, self.user)

        self.assertEqual(
            RoleRight.objects.filter(
                role_id=self.role.id, validity_to__isnull=True
            ).count(),
            0,
        )

    def test_omitting_rights_id_leaves_rights_untouched(self):
        update_or_create_role({"uuid": self.role.uuid, "name": "Renamed"}, self.user)

        self.assertEqual(
            RoleRight.objects.filter(
                role_id=self.role.id, validity_to__isnull=True
            ).count(),
            2,
        )

    def test_duplicate_right_in_input_creates_one_row(self):
        update_or_create_role({"uuid": self.role.uuid, "rights_id": []}, self.user)
        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A, _RIGHT_A]}, self.user
        )

        self.assertEqual(self._open_rows(_RIGHT_A).count(), 1)

    def test_update_records_the_acting_user_not_the_creator(self):
        other = create_test_interactive_user(username="RoleVersioningOtherUser")

        update_or_create_role(
            {
                "uuid": self.role.uuid,
                "rights_id": [_RIGHT_A, _RIGHT_B, _RIGHT_C],
            },
            other,
        )

        role = Role.objects.get(uuid=self.role.uuid)
        self.assertEqual(role.audit_user_id, other.i_user.id)
        self.assertEqual(
            self._open_rows(_RIGHT_C).first().audit_user_id, other.i_user.id
        )

    def test_revocation_preserves_the_granting_user(self):
        granter_id = self._open_rows(_RIGHT_B).first().audit_user_id
        other = create_test_interactive_user(username="RoleVersioningRevokeUser")

        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A]}, other
        )

        # audit_user_id on a RoleRight row identifies who granted the right.
        # Revoking must not overwrite it — the revoker cannot be recorded on
        # this row without a schema change, and losing the granter would be
        # worse than not knowing the revoker.
        closed_row = self._rows(_RIGHT_B).filter(validity_to__isnull=False).first()
        self.assertEqual(closed_row.audit_user_id, granter_id)

    def test_a_failed_update_leaves_no_orphan_history_row(self):
        # save_history() writes a Role clone before the rights are touched.
        # If the rights update then fails and the function is not atomic, that
        # clone survives and the change feed renders it as a phantom change.
        history_before = Role.objects.filter(legacy_id=self.role.id).count()

        with patch.object(
            RoleRight.objects, "create", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                update_or_create_role(
                    {
                        "uuid": self.role.uuid,
                        "rights_id": [_RIGHT_A, _RIGHT_B, _RIGHT_C],
                    },
                    self.user,
                )

        self.assertEqual(
            Role.objects.filter(legacy_id=self.role.id).count(), history_before
        )

    def test_pre_existing_duplicate_rows_do_not_crash_the_update(self):
        # duplicate_role can leave two open rows for the same (role, right).
        # The old code raised MultipleObjectsReturned here.
        RoleRight.objects.create(
            role_id=self.role.id, right_id=_RIGHT_A, audit_user_id=1
        )

        update_or_create_role(
            {"uuid": self.role.uuid, "rights_id": [_RIGHT_A, _RIGHT_B]}, self.user
        )

        self.assertEqual(self._open_rows(_RIGHT_A).count(), 2)
