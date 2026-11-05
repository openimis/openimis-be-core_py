"""The validity / audits contract of Model.get_queryset (OP-2029).

Two independent dimensions decide which rows come back, on top of row
security:

- validity: NOW (default), ALL, DELETED_NOW, at(date), between(from, to)
- audits:   NONE (default), ALL, at(date), between(from, to)

Every model family records deletion and history differently; these tests
pin the meaning of each value per family so the GraphQL contract can rely on
it. History / HistoryBusiness models have no concrete model in core and are
covered in the modules that define them.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase

from core.models import InteractiveUser, Role
from core.models.row_filters import Audits, Validity
from core.test_helpers import create_test_interactive_user, create_test_role


def ids(queryset):
    return set(queryset.values_list("id", flat=True))


class VersionedModelRowsTest(TestCase):
    """validity_to marks a deleted row, legacy_id an audit copy."""

    @classmethod
    def setUpTestData(cls):
        cls.current = create_test_role(name="row-filters-current")
        cls.edited = create_test_role(name="row-filters-edited")
        cls.audit_copy_id = cls.edited.save_history()
        cls.deleted = create_test_role(name="row-filters-deleted")
        cls.deleted.delete_history()
        # delete_history() keeps the last live state as an audit copy too
        cls.deleted_copy_id = Role.objects.get(legacy_id=cls.deleted.id).id
        cls.mine = Role.objects.filter(name__startswith="row-filters-")
        cls.user = create_test_interactive_user(username="rowfiltersrole")

    def rows(self, **kwargs):
        return ids(Role.get_queryset(self.mine, self.user, **kwargs))

    def test_now_is_current_rows_only(self):
        self.assertEqual(
            {self.current.id, self.edited.id},
            self.rows(validity=Validity.NOW),
        )

    def test_all_adds_deleted_rows_but_no_audit_copy(self):
        self.assertEqual(
            {self.current.id, self.edited.id, self.deleted.id},
            self.rows(validity=Validity.ALL),
        )

    def test_deleted_now_is_deleted_rows_only(self):
        self.assertEqual({self.deleted.id}, self.rows(validity=Validity.DELETED_NOW))

    def test_audits_all_adds_the_audit_copy(self):
        self.assertEqual(
            {self.current.id, self.edited.id, self.audit_copy_id, self.deleted_copy_id},
            self.rows(validity=Validity.NOW, audits=Audits.ALL),
        )

    def test_audits_between_is_dated_on_the_change(self):
        now = datetime.now()
        self.assertIn(
            self.audit_copy_id,
            self.rows(audits=Audits.between(now - timedelta(days=1), now + timedelta(days=1))),
        )
        self.assertNotIn(
            self.audit_copy_id,
            self.rows(audits=Audits.between(now - timedelta(days=3), now - timedelta(days=2))),
        )

    def test_a_validity_date_on_an_audit_only_table_is_refused(self):
        with self.assertRaises(ValueError):
            Role.get_queryset(self.mine, self.user, validity=Validity.at(datetime.now()))

    def test_a_validity_date_on_a_business_versioned_table_is_the_version_valid_then(self):
        with patch.object(Role, "business_versioned", True, create=True):
            before = datetime.now() - timedelta(days=30)
            self.assertEqual(set(), self.rows(validity=Validity.at(before)))
            self.assertTrue(
                {self.current.id, self.edited.id} <= self.rows(validity=Validity.at(datetime.now()))
            )

    def test_without_arguments_the_model_keeps_its_own_default(self):
        # Phase 1 changes no runtime behaviour: a caller that says nothing
        # gets what it got before the contract existed.
        self.assertEqual(
            ids(self.mine),
            ids(Role.get_queryset(self.mine, self.user)),
        )


class OpenIMISMigrationModelRowsTest(TestCase):
    """active and validity_to both mark deletion; audits live in the history table."""

    @classmethod
    def setUpTestData(cls):
        cls.current = create_test_interactive_user(username="rowfilters_current")
        cls.deleted = create_test_interactive_user(username="rowfilters_deleted")
        cls.deleted.i_user.delete_history()
        cls.mine = InteractiveUser.objects.filter(login_name__startswith="rowfilters_")
        cls.user = create_test_interactive_user(username="rowfiltersiuser")

    def rows(self, **kwargs):
        return ids(InteractiveUser.get_queryset(self.mine, self.user, **kwargs))

    def test_now_hides_deleted(self):
        self.assertEqual({self.current.i_user.id}, self.rows(validity=Validity.NOW))

    def test_deleted_now(self):
        self.assertEqual({self.deleted.i_user.id}, self.rows(validity=Validity.DELETED_NOW))

    def test_all(self):
        self.assertEqual(
            {self.current.i_user.id, self.deleted.i_user.id},
            self.rows(validity=Validity.ALL),
        )

    def test_a_validity_date_is_refused(self):
        with self.assertRaises(ValueError):
            InteractiveUser.get_queryset(self.mine, self.user, validity=Validity.at(datetime.now()))

    def test_audits_come_from_the_history_table(self):
        i_user = self.current.i_user
        i_user.other_names = "renamed"
        i_user.save()
        audit = InteractiveUser.get_audit_queryset(self.user, audits=Audits.ALL).filter(id=i_user.id)
        self.assertTrue(audit.exists())
        self.assertIn("renamed", set(audit.values_list("other_names", flat=True)))

    def test_audits_on_the_main_query_are_refused(self):
        # The history table is another model; the main query cannot return it.
        with self.assertRaises(ValueError):
            InteractiveUser.get_queryset(self.mine, self.user, audits=Audits.ALL)


class NoRowsTest(TestCase):
    def test_no_rows_is_empty_and_still_a_queryset(self):
        qs = Role.no_rows()
        self.assertEqual(0, qs.count())
        self.assertEqual(Role, qs.model)


class RowFilterValuesTest(TestCase):
    def test_between_needs_an_ordered_range(self):
        now = datetime.now()
        with self.assertRaises(ValueError):
            Validity.between(now, now - timedelta(days=1))

    def test_constants_are_distinct(self):
        self.assertNotEqual(Validity.NOW, Validity.ALL)
        self.assertNotEqual(Audits.NONE, Audits.ALL)


class ApplyRowFiltersTest(TestCase):
    """What an overriding get_queryset opens with."""

    @classmethod
    def setUpTestData(cls):
        cls.current = create_test_role(name="apply-rows-current")
        cls.deleted = create_test_role(name="apply-rows-deleted")
        cls.deleted.delete_history()
        cls.mine = Role.objects.filter(name__startswith="apply-rows-")

    def test_nothing_asked_leaves_the_queryset(self):
        self.assertEqual(ids(self.mine), ids(Role.apply_row_filters(self.mine)))

    def test_nothing_asked_applies_the_given_default(self):
        self.assertEqual(
            ids(Role.filter_queryset(self.mine)),
            ids(Role.apply_row_filters(self.mine, default=Role.filter_queryset)),
        )

    def test_a_request_wins_over_the_default(self):
        self.assertEqual(
            {self.deleted.id},
            ids(Role.apply_row_filters(
                self.mine, validity=Validity.DELETED_NOW, default=Role.filter_queryset
            )),
        )
