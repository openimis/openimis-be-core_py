import graphene
from django.test import SimpleTestCase

from core.middleware import EnumValuesMiddleware

Colour = graphene.Enum("Colour", [("RED", "red"), ("BLUE", "blue")])


class _Filter(graphene.InputObjectType):
    colours = graphene.List(Colour)
    nested = graphene.Field(lambda: _Nested)


class _Nested(graphene.InputObjectType):
    colour = Colour()
    # A field named like a dict method: input objects are dicts with attributes.
    items = graphene.List(Colour)


received = {}


class _Query(graphene.ObjectType):
    echo = graphene.String(colour=Colour(), flt=_Filter())

    def resolve_echo(self, info, colour=None, flt=None):
        received["colour"] = colour
        received["flt"] = flt
        return "ok"


class EnumValuesMiddlewareTest(SimpleTestCase):
    # graphene 2 handed resolvers the enum's value ("red"); graphene 3 hands them
    # the Python enum member. Module code compares and stores the raw values.

    def execute(self, query):
        received.clear()
        result = graphene.Schema(query=_Query).execute(query, middleware=[EnumValuesMiddleware()])
        self.assertIsNone(result.errors)

    def test_enum_argument_reaches_the_resolver_as_its_value(self):
        self.execute("{ echo(colour: RED) }")
        self.assertEqual(received["colour"], "red")

    def test_enums_inside_input_objects_and_lists_are_values_too(self):
        self.execute("{ echo(flt: {colours: [RED, BLUE], nested: {colour: BLUE}}) }")
        self.assertEqual(received["flt"]["colours"], ["red", "blue"])
        self.assertEqual(received["flt"]["nested"]["colour"], "blue")

    def test_input_field_named_items_is_converted_on_key_and_attribute(self):
        self.execute("{ echo(flt: {nested: {colour: RED, items: [BLUE]}}) }")
        nested = received["flt"]["nested"]
        self.assertEqual(nested["items"], ["blue"])
        self.assertEqual(nested.colour, "red")
