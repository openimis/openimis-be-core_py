"""Numeric strings accepted for Int and Float variables, as with graphene 2.

graphene 2 coerced a variable such as {"location": "70"} for `$location: Int` to
70; the frontend relies on it in several queries. graphene 3 maps Int and Float
onto graphql-core 3's built-in scalars, which refuse strings. Only variable
values are concerned: output already accepts numeric strings, and a string
literal in the query text was refused by graphene 2 as well.
"""
from graphql import GraphQLFloat, GraphQLInt


def _numeric_string_first(parse_value, convert):
    def parse(value):
        if isinstance(value, str):
            try:
                value = convert(value.strip())
            except ValueError:
                pass  # not numeric: let the scalar refuse it with its own message
        return parse_value(value)

    parse.lenient = True
    return parse


def _int(value):
    try:
        return int(value)
    except ValueError:
        number = float(value)
        if not number.is_integer():
            raise
        return int(number)


def register_lenient_number_variables():
    """Called from CoreConfig.ready(); patching twice is harmless."""
    if not getattr(GraphQLInt.parse_value, "lenient", False):
        GraphQLInt.parse_value = _numeric_string_first(GraphQLInt.parse_value, _int)
    if not getattr(GraphQLFloat.parse_value, "lenient", False):
        GraphQLFloat.parse_value = _numeric_string_first(GraphQLFloat.parse_value, float)
