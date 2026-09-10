from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from core.models import InteractiveUser, Role, RoleRight, UserRole
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

    def test_removing_every_right_from_a_role_invalidates_rights_cache(self):
        from core.schema import update_or_create_role

        self.assertEqual([BASE_RIGHT_ID], self.i_user.rights)

        # rights_id=[] expires the role rights with a queryset update, which
        # fires no post_save: the mutation has to invalidate explicitly
        update_or_create_role(
            {"uuid": str(self.role.uuid), "name": self.role.name, "rights_id": []},
            self.user,
        )

        self.assertEqual(
            [], InteractiveUser.objects.get(id=self.i_user.id).rights
        )

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


class RecordingCacheStub:
    """Records what the receivers ask the cache to drop."""

    def __init__(self):
        self.deleted_keys = []
        self.cleared = False

    def get(self, key, default=None):
        return default

    def set(self, key, value, timeout=None):
        pass

    def delete(self, key):
        self.deleted_keys.append(key)

    def delete_many(self, keys):
        self.deleted_keys.extend(keys)

    def clear(self):
        self.cleared = True


class BrokenCacheStub:
    """Stands in for an unreachable cache backend (e.g. redis is down)."""

    def _fail(self, *args, **kwargs):
        raise ConnectionError("Error -3 connecting to redis:6379.")

    get = set = delete = clear = _fail
    get_many = set_many = delete_many = _fail


class RoleChangeCacheInvalidationTest(TestCase):
    def setUp(self):
        self.role = create_role("TestRoleChangeCacheRole")
        self.user = create_test_interactive_user(
            username="TestRoleChangeCacheUser", roles=[self.role.id]
        )
        self.i_user = self.user.i_user

    def test_role_change_drops_the_keys_of_its_members(self):
        stub = RecordingCacheStub()

        with patch("core.cache_control.cache", stub):
            self.role.name = "TestRoleChangeCacheRoleRenamed"
            self.role.save()

        self.assertIn(f"rights_{self.i_user.id}", stub.deleted_keys)
        self.assertIn(f"is_admin_{self.i_user.id}", stub.deleted_keys)

    def test_role_right_change_drops_the_keys_of_the_role_members(self):
        stub = RecordingCacheStub()

        with patch("core.cache_control.cache", stub):
            RoleRight.objects.create(
                role=self.role, right_id=OTHER_ROLE_RIGHT_ID, audit_user_id=-1
            )

        self.assertIn(f"rights_{self.i_user.id}", stub.deleted_keys)

    def test_role_change_never_flushes_the_whole_cache(self):
        # cache.clear() is a FLUSHDB on redis: it would take the location and
        # coverage caches (same instance, different KEY_PREFIX) with it
        stub = RecordingCacheStub()

        with patch("core.cache_control.cache", stub):
            self.role.name = "TestRoleChangeCacheRoleRenamedAgain"
            self.role.save()

        self.assertFalse(stub.cleared)

    def test_role_change_leaves_non_members_alone(self):
        other_role = create_role("TestRoleChangeCacheOtherRole")
        stub = RecordingCacheStub()

        with patch("core.cache_control.cache", stub):
            other_role.name = "TestRoleChangeCacheOtherRoleRenamed"
            other_role.save()

        self.assertNotIn(f"rights_{self.i_user.id}", stub.deleted_keys)


class UnreachableCacheTest(TestCase):
    """A cache backend that is down must not break the database write."""

    def setUp(self):
        self.role = create_role("TestUnreachableCacheRole")
        self.user = create_test_interactive_user(
            username="TestUnreachableCacheUser", roles=[self.role.id]
        )
        self.i_user = self.user.i_user

    def test_role_save_succeeds_when_cache_is_unreachable(self):
        with patch("core.cache_control.cache", BrokenCacheStub()):
            self.role.name = "TestUnreachableCacheRoleRenamed"
            self.role.save()

        self.role.refresh_from_db()
        self.assertEqual(self.role.name, "TestUnreachableCacheRoleRenamed")

    def test_role_right_save_succeeds_when_cache_is_unreachable(self):
        with patch("core.cache_control.cache", BrokenCacheStub()):
            right = RoleRight.objects.create(
                role=self.role,
                right_id=OTHER_ROLE_RIGHT_ID,
                audit_user_id=-1,
            )

        self.assertTrue(RoleRight.objects.filter(id=right.id).exists())

    def test_user_role_save_succeeds_when_cache_is_unreachable(self):
        other_role = create_role("TestUnreachableCacheOtherRole")

        with patch("core.cache_control.cache", BrokenCacheStub()):
            user_role = UserRole.objects.create(
                user=self.i_user, role=other_role, audit_user_id=-1
            )

        self.assertTrue(UserRole.objects.filter(id=user_role.id).exists())

    def test_object_cache_write_succeeds_when_cache_is_unreachable(self):
        # the model cache (CachedModelMixin.update_cache) is the other caller
        # that used to take the save down with it
        with patch.object(Role, "USE_CACHE", True), patch(
            "core.cache_control.cache", BrokenCacheStub()
        ):
            self.role.name = "TestUnreachableCacheRoleCached"
            self.role.save()

        self.role.refresh_from_db()
        self.assertEqual(self.role.name, "TestUnreachableCacheRoleCached")

    def test_rights_read_falls_back_to_the_database_when_cache_is_unreachable(self):
        RoleRight.objects.create(
            role=self.role, right_id=BASE_RIGHT_ID, audit_user_id=-1
        )

        with patch("core.cache_control.cache", BrokenCacheStub()):
            rights = InteractiveUser.objects.get(id=self.i_user.id).rights

        self.assertIn(BASE_RIGHT_ID, rights)
