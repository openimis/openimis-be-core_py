from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from core.models import Role, RoleRight, UserRole
from core.test_helpers import create_test_interactive_user

BASE_RIGHT_ID = 999000
ADDED_RIGHT_ID = 999001
OTHER_ROLE_RIGHT_ID = 999002


def create_role(name):
    return Role.objects.create(
        name=name, is_system=0, is_blocked=False, audit_user_id=-1
    )


class RightsCacheInvalidationTest(TestCase):
    def setUp(self):
        self.role = create_role("TestRightsCacheRole")
        RoleRight.objects.create(
            role=self.role, right_id=BASE_RIGHT_ID, audit_user_id=-1
        )
        self.user = create_test_interactive_user(
            username="TestRightsCacheUser", roles=[self.role.id]
        )
        self.i_user = self.user.i_user
        cache.clear()

    def test_adding_role_right_invalidates_rights_cache(self):
        self.assertEqual([BASE_RIGHT_ID], self.i_user.rights)

        RoleRight.objects.create(
            role=self.role, right_id=ADDED_RIGHT_ID, audit_user_id=-1
        )

        self.assertIn(ADDED_RIGHT_ID, self.i_user.rights)

    def test_removing_role_right_invalidates_rights_cache(self):
        role_right = RoleRight.objects.create(
            role=self.role, right_id=ADDED_RIGHT_ID, audit_user_id=-1
        )
        cache.clear()
        self.assertIn(ADDED_RIGHT_ID, self.i_user.rights)

        role_right.delete()

        self.assertNotIn(ADDED_RIGHT_ID, self.i_user.rights)
        self.assertIn(BASE_RIGHT_ID, self.i_user.rights)

    def test_assigning_role_to_user_invalidates_rights_cache(self):
        other_role = create_role("TestRightsCacheOtherRole")
        RoleRight.objects.create(
            role=other_role, right_id=OTHER_ROLE_RIGHT_ID, audit_user_id=-1
        )
        cache.clear()
        self.assertEqual([BASE_RIGHT_ID], self.i_user.rights)

        UserRole.objects.create(user=self.i_user, role=other_role, audit_user_id=-1)

        self.assertIn(OTHER_ROLE_RIGHT_ID, self.i_user.rights)

    def test_assigning_admin_role_invalidates_is_admin_cache(self):
        admin_role = Role.objects.create(
            name="TestRightsCacheAdminRole",
            is_system=64,
            is_blocked=False,
            audit_user_id=-1,
        )
        self.assertFalse(self.i_user.is_imis_admin)

        UserRole.objects.create(user=self.i_user, role=admin_role, audit_user_id=-1)

        self.assertTrue(self.i_user.is_imis_admin)


class PatternCacheStub:
    def __init__(self, supports_patterns):
        self.deleted_keys = []
        self.deleted_patterns = []
        self.cleared = False
        if supports_patterns:
            self.delete_pattern = self._delete_pattern

    def _delete_pattern(self, pattern):
        self.deleted_patterns.append(pattern)

    def delete(self, key):
        self.deleted_keys.append(key)

    def clear(self):
        self.cleared = True


class RoleChangeCacheInvalidationTest(TestCase):
    def setUp(self):
        self.role = create_role("TestRoleChangeCacheRole")

    def test_role_change_deletes_rights_keys_by_pattern_when_supported(self):
        stub = PatternCacheStub(supports_patterns=True)

        with patch("core.receivers.cache", stub):
            self.role.name = "TestRoleChangeCacheRoleRenamed"
            self.role.save()

        self.assertIn("rights_*", stub.deleted_patterns)
        self.assertFalse(stub.cleared)

    def test_role_change_deletes_is_admin_keys_by_pattern_when_supported(self):
        stub = PatternCacheStub(supports_patterns=True)

        with patch("core.receivers.cache", stub):
            self.role.is_system = 64
            self.role.save()

        self.assertIn("is_admin_*", stub.deleted_patterns)

    def test_role_change_clears_cache_when_patterns_unsupported(self):
        stub = PatternCacheStub(supports_patterns=False)

        with patch("core.receivers.cache", stub):
            self.role.name = "TestRoleChangeCacheRoleRenamed"
            self.role.save()

        self.assertTrue(stub.cleared)
