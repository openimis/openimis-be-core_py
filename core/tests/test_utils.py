import datetime
import uuid
import decimal
from django.test import TestCase
from django.db.models import Q

from core.utils import (
    full_class_name, comparable, to_json_safe_value,
    to_list_permissions, collect_all_gql_permissions,
    clear_current_user, clear_history_context
)
from core.datetimes.ad_datetime import AdDate, AdDatetime
from core.test_helpers import create_test_interactive_user
from core.models import User, RoleRight, UserRole, Role
from django.core.cache import caches


class ComparableTest(TestCase):
    def test_generic_eq(self):
        @comparable
        class A(object):
            def __init__(self, f):
                self.f = f

            def __eq__(self, other):
                return self.f == other.f

        @comparable
        class B(object):
            def __init__(self, f):
                self.f = f

            def __eq__(self, other):
                return self.f == other.f

        obj1 = A(f="a")
        obj2 = A(f="a")
        self.assertEqual(obj1, obj2)
        obj3 = B(f="b")
        self.assertNotEqual(obj1, obj3)
        obj4 = B(f="a")
        self.assertNotEqual(obj1, obj4)


class UtilsTestCase(TestCase):
    def test_full_class_name(self):
        self.assertEqual(full_class_name(self), "core.tests.test_utils.UtilsTestCase")

        self.assertEqual(full_class_name(1), "int")

    def test_json_serialize_value(self):
        self.assertEqual(to_json_safe_value(42), 42)
        self.assertEqual(to_json_safe_value("foo"), "foo")

        uuid_obj = uuid.uuid4()
        self.assertEqual(to_json_safe_value(uuid_obj), str(uuid_obj))

        date_obj = datetime.date(2025, 1, 1)
        self.assertEqual(to_json_safe_value(date_obj), str(date_obj))

        ad_date_obj = AdDate(2025, 1, 1)
        self.assertEqual(to_json_safe_value(ad_date_obj), str(ad_date_obj))

        ad_datetime_obj = AdDatetime(2025, 1, 1, 12, 0, 0)
        self.assertEqual(to_json_safe_value(ad_datetime_obj), str(ad_datetime_obj))

        decimal_obj = decimal.Decimal("12345.6789")
        self.assertEqual(to_json_safe_value(decimal_obj), str(decimal_obj))

    def test_is_admin_rights(self):
        if not User.objects.filter(username="Admin").exists():
            User.objects.create_superuser(username="Admin", password="S/pe®Pąßw0rd™")
        user = User.objects.filter(username="Admin").first()
        # ensure superuser flag (some create paths may not persist it visibly without explicit set/refresh)
        if not user.is_superuser:
            user.is_superuser = True
            user.save()
        if user.i_user and not user.i_user.is_superuser:
            # will delegate to core, but force via core
            pass
        # removing all role but admin
        UserRole.objects.filter(
            ~Q(role__is_system=64), user=user._u, *UserRole.filter_validity()
        ).delete()
        # removing all admin rights
        RoleRight.objects.filter(role__is_system=64, *RoleRight.filter_validity()).delete()
        clear_current_user()
        clear_history_context()
        caches["default"].clear()
        # also clear any rights cache specifically
        caches["default"].delete("rights_" + str(getattr(user.i_user, "id", "")))
        rights = list(user.rights)
        rights_db = [
            rr.right_id
            for rr in RoleRight.filter_queryset()
            .filter(role__is_system=64, *RoleRight.filter_validity(prefix="role__"))
            .distinct()
        ]
        self.assertEqual(len(rights_db), 0, "all roleright are not removed")
        self.assertEqual(
            len(rights),
            len(to_list_permissions()),
            "rights are not equal to all right available",
        )
        self.assertNotEqual(
            len(rights_db), len(rights),
            "admin should always get all permissions regardless of their RoleRight stored in DB"
        )
    CORE_PERMS = [
        121701, 121702, 121703, 121704,
        122001, 122002, 122003, 122006, 122005, 122004,
        121501, 121502, 121503, 121504,
        121601, 121602, 121603, 121604,
        900101, 122000
    ]

    def test_collect_all_gql_permissions(self):
        perms = collect_all_gql_permissions()
        self.assertTrue('core' in perms)
        core_perms = perms['core']
        all_core_perm = []
        for core_perms in perms['core'].values():
            for core_perm in core_perms:
                all_core_perm.append(int(core_perm))
        self.assertEqual(sorted(all_core_perm), sorted(self.CORE_PERMS), "Missmatch for the expected core perms")

    def test_to_list_permissions(self):
        perm_list = to_list_permissions()
        for perm in self.CORE_PERMS:
            self.assertTrue((perm) in perm_list, f"This perm {perm} from core is not return ")

    def test_cache_invalidation(self):
        User.USE_CACHE = True
        create_test_interactive_user(username="one")
        create_test_interactive_user(username="two")
        users = list(User.objects.all())
        users_id = [user.id for user in users]
        # get 0 without cache
        users_0_no_cache_get = User.objects.get(id=users_id[0], *User.filter_validity())
        # get 0 with cache
        users_0_filter = User.objects.filter(id=users_id[0]).first()
        # get 1 with cache
        users_1_filter = User.objects.filter(id=users_id[-1]).first()
        self.assertEqual(
            users_0_no_cache_get,
            users_0_filter,
            "get and filter should retrieve the same object",
        )
        # update 1, cache should be invalidaed
        users_0_filter.username = users_0_filter.username + "T"
        users_0_filter.save()
        # get use from cache / partially from cache
        users_filter = list(User.objects.filter(id__in=users_id))
        users_0_filter = User.objects.filter(id=users_id[0]).first()
        self.assertNotEqual(
            users_0_no_cache_get.username,
            users_0_filter.username,
            "the object should be different, cache not invalidated properly",
        )
        # remove user 1 from cache
        caches["default"].delete(f"cd_User_{users_1_filter.id}")
        # remove user 1 from all user list (old and new)
        users.remove(users_0_no_cache_get)
        users_filter.remove(users_0_filter)
        self.assertEqual(
            sorted(users, key=lambda x: x.id),
            sorted(users_filter, key=lambda x: x.id),
            "should be the same list even if user_filter comes partially from cache",
        )
        caches["default"].clear()
        User.USE_CACHE = False
