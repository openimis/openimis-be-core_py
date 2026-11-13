"""OP-3317: the GraphQL connection arguments mapped onto Model.get_queryset's
validity / audits (OP-2029), and the legacy defaults a resolver states for the
arguments the frontend already sends."""
from types import SimpleNamespace

from django.test import TestCase

from core.gql.row_filter_args import (
    legacy_row_filters, row_filter_kwargs, row_filters_from_args, row_filters_in_context)
from core.gql.scoped_object_type import ScopedQuerysetMixin
from core.models.row_filters import Audits, Validity


class GraphQLArgumentMappingTest(TestCase):
    """OP-3317 phase 2: old connection arguments -> validity / audits."""

    def test_show_history_asks_for_audits(self):
        self.assertEqual(Audits.ALL, row_filters_from_args({"showHistory": True})["audits"])

    def test_is_deleted_maps_to_validity(self):
        self.assertEqual(Validity.DELETED_NOW, row_filters_from_args({"isDeleted": True})["validity"])
        self.assertEqual(Validity.LIVE, row_filters_from_args({"isDeleted": False})["validity"])
        self.assertEqual(Validity.ALL, row_filters_from_args({"isDeleted": None})["validity"])

    def test_nothing_asked_maps_to_nothing(self):
        self.assertEqual({}, row_filters_from_args({"first": 10}))

    def test_legacy_defaults_reach_the_model_under_explicit_arguments(self):
        info = SimpleNamespace(context=SimpleNamespace())
        model = SimpleNamespace(get_business_validity_fields=lambda: None)
        # the resolver runs first and states what its legacy arguments mean
        rows = legacy_row_filters(info, {"showHistory": True}, validity=Validity.ALL, audits=Audits.ALL)
        self.assertEqual({"validity": Validity.ALL, "audits": Audits.ALL}, rows)
        with row_filters_in_context(info, {"showHistory": True}):
            self.assertEqual({"validity": Validity.ALL, "audits": Audits.ALL}, row_filter_kwargs(model, info))
        # an explicit isDeleted overrides the legacy validity
        rows = legacy_row_filters(info, {"isDeleted": False}, validity=Validity.ALL)
        self.assertEqual({"validity": Validity.LIVE}, rows)
        with row_filters_in_context(info, {"isDeleted": False}):
            self.assertEqual({"validity": Validity.LIVE}, row_filter_kwargs(model, info))

    def test_legacy_defaults_do_not_leak_into_the_next_field(self):
        info = SimpleNamespace(context=SimpleNamespace())
        model = SimpleNamespace(get_business_validity_fields=lambda: None)
        legacy_row_filters(info, {}, validity=Validity.ALL)
        with row_filters_in_context(info, {}):
            self.assertEqual({"validity": Validity.ALL}, row_filter_kwargs(model, info))
        with row_filters_in_context(info, {}):
            self.assertEqual({}, row_filter_kwargs(model, info))

    def test_dates_only_reach_business_validity_models(self):
        info = SimpleNamespace(context=SimpleNamespace())
        business = SimpleNamespace(get_business_validity_fields=lambda: ("date_valid_from", "date_valid_to"))
        plain = SimpleNamespace(get_business_validity_fields=lambda: None)
        with row_filters_in_context(info, {"dateValidFrom__Gte": "2020-01-01"}):
            self.assertEqual("between", row_filter_kwargs(business, info)["validity"].kind)
            self.assertEqual({}, row_filter_kwargs(plain, info))
        self.assertEqual({}, row_filter_kwargs(business, info))

    def test_scoped_type_passes_the_mapping_to_the_model(self):
        calls = []

        class Model:
            @classmethod
            def get_queryset(cls, queryset, user, *, validity=None, audits=None):
                calls.append((user, validity, audits))
                return queryset

            @classmethod
            def get_business_validity_fields(cls):
                return None

        class Type(ScopedQuerysetMixin):
            _meta = SimpleNamespace(model=Model)

        user = object()
        info = SimpleNamespace(context=SimpleNamespace(user=user))
        with row_filters_in_context(info, {"showHistory": True}):
            Type.get_queryset("qs", info)
        Type.get_queryset("qs", info)
        self.assertEqual([(user, None, Audits.ALL), (user, None, None)], calls)

    def test_an_old_signature_still_works(self):
        class Model:
            @classmethod
            def get_queryset(cls, queryset, user):
                return queryset

        class Type(ScopedQuerysetMixin):
            _meta = SimpleNamespace(model=Model)

        info = SimpleNamespace(context=SimpleNamespace(user=None))
        with row_filters_in_context(info, {"showHistory": True}):
            self.assertEqual("qs", Type.get_queryset("qs", info))
