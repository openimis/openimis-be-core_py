import graphene
from django.test import SimpleTestCase

from core.gql import HistoryTypeEnum


class _Row:
    def __init__(self, history_type):
        self.history_type = history_type


class _HistoryRow(graphene.ObjectType):
    history_type = graphene.Field(HistoryTypeEnum, required=True)


class _Query(graphene.ObjectType):
    rows = graphene.List(graphene.NonNull(_HistoryRow))

    def resolve_rows(self, info):
        # The raw values django-simple-history stores in history_type.
        return [_Row("+"), _Row("~"), _Row("-")]


class HistoryTypeEnumTest(SimpleTestCase):
    def test_schema_with_history_type_is_valid(self):
        # graphql-core 3 rejects the names graphene-django derives from the raw
        # choices ("_", "__1", "__2"): "__" is reserved for introspection.
        schema = graphene.Schema(query=_Query)
        self.assertIn("enum HistoryType", str(schema))

    def test_raw_values_serialize_to_names(self):
        result = graphene.Schema(query=_Query).execute("{ rows { historyType } }")
        self.assertIsNone(result.errors)
        self.assertEqual(
            [row["historyType"] for row in result.data["rows"]],
            ["CREATED", "CHANGED", "DELETED"],
        )
