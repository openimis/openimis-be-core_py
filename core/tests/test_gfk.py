"""
OP-3343: prefetch_gfk() loads the GenericForeignKey targets of a page in a fixed
number of queries, shares them between rows, loads the requested relations with
them, and only loads what the GraphQL query asks for.
"""
from types import SimpleNamespace

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from graphql import parse

from core.gfk import prefetch_gfk, requested_fields
from core.models import User, UserBusinessAccess
from core.test_helpers import create_test_interactive_user


def _info(query):
    document = parse(query)
    operation, *fragments = document.definitions
    return SimpleNamespace(
        field_nodes=[operation.selection_set.selections[0]],
        fragments={fragment.name.value: fragment for fragment in fragments},
    )


class PrefetchGfkTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = create_test_interactive_user(username="gfk3343_owner")
        cls.targets = [create_test_interactive_user(username=f"gfk3343_{i}") for i in range(3)]
        user_type = ContentType.objects.get_for_model(User)
        # Rows 0 and 3 point at the same user.
        for i, target in enumerate(cls.targets + cls.targets[:1]):
            UserBusinessAccess.objects.create(
                user=cls.owner, content_type=user_type, object_id=str(target.id), link_type=f"gfk3343_{i}")

    def _rows(self, count, **kwargs):
        queryset = UserBusinessAccess.objects.filter(link_type__startswith="gfk3343_").order_by("link_type")
        return prefetch_gfk(queryset[:count], "content_object", **kwargs)

    def _read(self, rows):
        with CaptureQueriesContext(connection) as ctx:
            values = [(row.content_type.model, row.content_object.username, row.content_object.i_user.login_name)
                      for row in rows]
        return len(ctx), values

    def test_query_count_does_not_depend_on_rows(self):
        few, _ = self._read(self._rows(2, related={"core.User": ("i_user",)}))
        many, values = self._read(self._rows(4, related={"core.User": ("i_user",)}))
        self.assertEqual(few, many)
        self.assertEqual([v[1] for v in values], [t.username for t in self.targets + self.targets[:1]])

    def test_without_prefetch_each_row_costs_queries(self):
        # The cost prefetch_gfk removes, so that the test above is known to measure it.
        queryset = UserBusinessAccess.objects.filter(link_type__startswith="gfk3343_").order_by("link_type")
        few, _ = self._read(queryset[:2])
        many, _ = self._read(queryset[:4])
        self.assertGreater(many, few)

    def test_rows_pointing_at_the_same_target_share_it(self):
        rows = list(self._rows(4))
        self.assertIs(rows[0].content_object, rows[3].content_object)

    def test_a_model_that_is_not_installed_is_skipped(self):
        rows = list(self._rows(4, related={"no_such_module.Model": ("x",), "core.User": ("i_user",)}))
        self.assertEqual(rows[1].content_object.username, self.targets[1].username)

    def test_with_info_only_the_requested_parts_are_loaded(self):
        queryset = UserBusinessAccess.objects.all()
        nothing = prefetch_gfk(queryset, "content_object", info=_info("{ a { edges { node { linkType } } } }"))
        self.assertEqual(nothing._prefetch_related_lookups, ())
        self.assertFalse(nothing.query.select_related)

        type_only = prefetch_gfk(queryset, "content_object", info=_info("{ a { edges { node { contentTypeName } } } }"))
        self.assertEqual(type_only._prefetch_related_lookups, ())
        self.assertEqual(type_only.query.select_related, {"content_type": {}})

        target = prefetch_gfk(
            queryset, "content_object", reads={"content_object": ("owner",)},
            info=_info("{ a { edges { node { ...F } } } } fragment F on X { owner }"))
        self.assertEqual(len(target._prefetch_related_lookups), 1)
        self.assertEqual(target.query.select_related, {"content_type": {}})

    def test_requested_fields_follows_fragments(self):
        info = _info("{ a { edges { node { id ...F ... on Y { z } } } } } fragment F on X { b { c } }")
        self.assertEqual(requested_fields(info), {"edges", "node", "id", "b", "c", "z"})

    def test_a_name_that_is_not_a_generic_foreign_key_is_refused(self):
        with self.assertRaises(ValueError):
            prefetch_gfk(UserBusinessAccess.objects.all(), "user")
