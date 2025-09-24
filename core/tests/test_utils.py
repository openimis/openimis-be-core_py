import datetime
import uuid
import decimal
from django.test import TestCase
from django.db.models import Q

from core.utils import full_class_name, comparable, to_json_safe_value
from core.datetimes.ad_datetime import AdDate, AdDatetime
from core.test_helpers import create_test_interactive_user


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
        self.assertEquals(obj1, obj2)
        obj3 = B(f="b")
        self.assertNotEquals(obj1, obj3)
        obj4 = B(f="a")
        self.assertNotEquals(obj1, obj4)


class UtilsTestCase(TestCase):
    def test_full_class_name(self):
        self.assertEquals(full_class_name(self), "core.tests.test_utils.UtilsTestCase")

        self.assertEquals(full_class_name(1), "int")

    def test_json_serialize_value(self):
        self.assertEquals(to_json_safe_value(42), 42)
        self.assertEquals(to_json_safe_value("foo"), "foo")

        uuid_obj = uuid.uuid4()
        self.assertEquals(to_json_safe_value(uuid_obj), str(uuid_obj))

        date_obj = datetime.date(2025, 1, 1)
        self.assertEquals(to_json_safe_value(date_obj), str(date_obj))

        ad_date_obj = AdDate(2025, 1, 1)
        self.assertEquals(to_json_safe_value(ad_date_obj), str(ad_date_obj))

        ad_datetime_obj = AdDatetime(2025, 1, 1, 12, 0, 0)
        self.assertEquals(to_json_safe_value(ad_datetime_obj), str(ad_datetime_obj))

        decimal_obj = decimal.Decimal("12345.6789")
        self.assertEquals(to_json_safe_value(decimal_obj), str(decimal_obj))

    def test_is_admin_rights(self):
        from core.models import User, RoleRight, UserRole, Role
        from core.utils import to_list_permissions, filter_validity
        role = Role.objects.filter(is_system=64, *filter_validity()).first()
        user = User.objects.filter(username="Admin", *filter_validity()).first()
        if not user:
            user = create_test_interactive_user(username="Admin", roles=[role.id])
        # removing all role but admin
        UserRole.objects.filter(
            ~Q(role__is_system=64), user=user._u, *filter_validity()
        ).delete()
        # removing all admin rights
        RoleRight.objects.filter(role__is_system=64, *filter_validity()).delete()
        rights = list(user.rights)
        rights_db = [
            rr.right_id
            for rr in RoleRight.filter_queryset()
            .filter(role__is_system=64, *filter_validity(prefix="role__"))
            .distinct()
        ]
        self.assertEquals(len(rights_db), 0, "all roleright are not removed")
        self.assertEquals(
            len(rights),
            len(to_list_permissions()),
            "rights are not equal to all right available",
        )
        self.assertNotEquals(
            len(rights_db), len(rights), "rights should not be null for admin"
        )

    def test_cache_invalidation(self):
        from core.models import User

        User.USE_CACHE = True
        from django.core.cache import caches

        users = list(User.objects.all())
        users_id = [user.id for user in users]
        users_0_no_cache_get = User.objects.get(id=users_id[0])
        users_0_filter = User.objects.filter(id=users_id[0]).first()
        self.assertEquals(
            users_0_no_cache_get,
            users_0_filter,
            "get and filter should retrieve the same object",
        )
        users_0_filter.username = users_0_filter.username + "T"
        users_0_filter.save()
        users_filter = list(User.objects.filter(id__in=users_id))
        caches["default"].delete(f"cd_User_{users_filter[2].id}")
        users.remove(users_0_no_cache_get)
        users_filter.remove(users_0_filter)
        users_0_filter = User.objects.filter(id=users_id[0]).first()
        self.assertNotEquals(
            users_0_no_cache_get.username,
            users_0_filter.username,
            "the object should be different, cache not invalidated properly",
        )
        self.assertNotEquals(
            users,
            users_filter,
            "should be the same list even if user_filter comes partially from cache",
        )
        caches["default"].clear()
        User.USE_CACHE = False
