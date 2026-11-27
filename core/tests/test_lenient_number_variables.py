import graphene
from django.test import SimpleTestCase

received = {}


class _Query(graphene.ObjectType):
    echo = graphene.String(location=graphene.Int(), ratio=graphene.Float())

    def resolve_echo(self, info, location=None, ratio=None):
        received["location"] = location
        received["ratio"] = ratio
        return "ok"


class LenientNumberVariablesTest(SimpleTestCase):
    # graphene 2 accepted a numeric string for an Int or Float variable, and the
    # frontend relies on it (a location id sent as "70" for $location: Int).
    # graphql-core 3 refuses it; core restores the graphene 2 coercion.

    def execute(self, query, variables):
        received.clear()
        return graphene.Schema(query=_Query).execute(query, variables=variables)

    def test_numeric_string_for_an_int_variable(self):
        result = self.execute("query ($l: Int) { echo(location: $l) }", {"l": "70"})
        self.assertIsNone(result.errors)
        self.assertEqual(received["location"], 70)

    def test_numeric_string_for_a_float_variable(self):
        result = self.execute("query ($r: Float) { echo(ratio: $r) }", {"r": "2.5"})
        self.assertIsNone(result.errors)
        self.assertEqual(received["ratio"], 2.5)

    def test_a_non_numeric_string_is_still_refused(self):
        result = self.execute("query ($l: Int) { echo(location: $l) }", {"l": "seventy"})
        self.assertIsNotNone(result.errors)
