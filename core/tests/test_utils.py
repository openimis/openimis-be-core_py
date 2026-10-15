import datetime
import uuid
import decimal
from django.test import TestCase
from django.db.models import Q

from core.utils import (
    full_class_name, comparable, to_json_safe_value,
    to_list_permissions, collect_all_gql_permissions,
    clear_current_user, clear_history_context, append_validity_filter,
    deleted_filter
)
from core.datetimes.ad_datetime import AdDate, AdDatetime
from core.test_helpers import create_test_interactive_user
from core.models import User, RoleRight, UserRole
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
        900101, 122000,
        # 900201: new right for /api/core/scheduled_jobs, which was on AllowAny.
        900201,
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


class AppendValidityFilterIsDeletedTest(TestCase):
    """The soft-delete scope now comes from here rather than get_queryset.

    get_queryset is never handed the filter arguments, so forcing the scope
    there made "show deleted" resolve to is_deleted=True AND is_deleted=False -
    an empty list for every row (OP-3180). The decision belongs where the
    arguments are visible.
    """

    @staticmethod
    def _is_deleted_clauses(filters):
        return [f for f in filters if "is_deleted" in str(f)]

    def test_hides_deleted_by_default(self):
        filters = append_validity_filter()

        self.assertEqual(self._is_deleted_clauses(filters), [Q(is_deleted=False)])

    def test_honours_an_explicit_request_for_deleted_rows(self):
        filters = append_validity_filter(isDeleted=True)

        self.assertEqual(self._is_deleted_clauses(filters), [Q(is_deleted=True)])

    def test_none_returns_both(self):
        filters = append_validity_filter(isDeleted=None)

        self.assertEqual(self._is_deleted_clauses(filters), [])

    def test_accepts_the_snake_case_spelling_from_python_callers(self):
        self.assertEqual(
            self._is_deleted_clauses(append_validity_filter(is_deleted=True)),
            [Q(is_deleted=True)],
        )
        self.assertEqual(self._is_deleted_clauses(append_validity_filter(is_deleted=None)), [])

    def test_camel_case_wins_when_both_are_given(self):
        filters = append_validity_filter(isDeleted=True, is_deleted=False)

        self.assertEqual(self._is_deleted_clauses(filters), [Q(is_deleted=True)])

    def test_does_not_disturb_the_date_validity_filters(self):
        without = append_validity_filter(isDeleted=None)
        with_default = append_validity_filter()

        # The only difference is the soft-delete clause.
        self.assertEqual(len(with_default), len(without) + 1)


class _StubField:
    def __init__(self, name):
        self.name = name


class _StubMeta:
    def __init__(self, names):
        self._names = names

    def get_fields(self):
        return [_StubField(n) for n in self._names]


class _StubModel:
    """Just enough model to exercise the field lookup."""

    def __init__(self, *names):
        self._meta = _StubMeta(names)


class DeletedFilterTest(TestCase):
    """One rule, two spellings.

    `active` and `is_deleted` are each other's negation. Which one a model uses
    is the model's business; "hide deleted unless asked" is stated once.
    """

    def test_is_deleted_model(self):
        model = _StubModel("id", "is_deleted")

        self.assertEqual(deleted_filter(model), Q(is_deleted=False))
        self.assertEqual(deleted_filter(model, True), Q(is_deleted=True))

    def test_active_model_gets_the_negated_clause(self):
        model = _StubModel("id", "active")

        self.assertEqual(deleted_filter(model), Q(active=True))
        self.assertEqual(deleted_filter(model, True), Q(active=False))

    def test_is_deleted_wins_when_a_model_has_both(self):
        # HistoryModel exposes `active` as a property over is_deleted; should a
        # model ever carry both columns, the explicit marker is the right one.
        model = _StubModel("is_deleted", "active")

        self.assertEqual(deleted_filter(model), Q(is_deleted=False))

    def test_no_marker_means_no_clause(self):
        self.assertIsNone(deleted_filter(_StubModel("id", "name")))

    def test_none_means_no_clause(self):
        self.assertIsNone(deleted_filter(_StubModel("is_deleted"), None))
        self.assertIsNone(deleted_filter(None))

    def test_real_legacy_model_resolves_to_active(self):
        # InteractiveUser is OpenIMISMigrationModel: `active`, no is_deleted.
        from core.models import InteractiveUser

        self.assertEqual(deleted_filter(InteractiveUser), Q(active=True))

    def test_append_validity_filter_routes_through_the_model(self):
        from core.models import InteractiveUser

        clauses = [
            f for f in append_validity_filter(model=InteractiveUser) if "active" in str(f)
        ]

        self.assertEqual(clauses, [Q(active=True)])

    def test_without_a_model_it_still_assumes_is_deleted(self):
        # Every current caller is a HistoryBusinessModel, so the default stays.
        clauses = [f for f in append_validity_filter() if "is_deleted" in str(f)]

        self.assertEqual(clauses, [Q(is_deleted=False)])
