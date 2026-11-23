"""relay ``node(id:)`` built with ``core.schema.node_field`` refuses anonymous callers.

``node`` reaches every relay type by global id, row-secured or not, so the
guard sits on the field rather than on each type. The schema here is a minimal
one: the assembly declares the real field, and module tests do not depend on
the assembly.
"""

from types import SimpleNamespace

import graphene
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphql_relay import to_global_id

from graphql_jwt.exceptions import JSONWebTokenError

from core.gql_queries import RoleGQLType
from core.schema import node_field
from core.test_helpers import create_test_interactive_user, create_test_role


class _Query(graphene.ObjectType):
    node = node_field()


_SCHEMA = graphene.Schema(query=_Query, types=[RoleGQLType])

NODE_QUERY = """
query ($id: ID!) {
  node(id: $id) {
    id
    ... on RoleGQLType { name }
  }
}
"""


class NodeFieldTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role = create_test_role(name="NodeFieldRole")
        cls.user = create_test_interactive_user(username="node_field_user")

    def _execute(self, user):
        return _SCHEMA.execute(
            NODE_QUERY,
            variables={"id": to_global_id("RoleGQLType", self.role.id)},
            context=SimpleNamespace(user=user),
        )

    def test_anonymous_caller_is_refused(self):
        result = self._execute(AnonymousUser())

        self.assertIsNotNone(result.errors)
        self.assertIsInstance(result.errors[0].original_error, JSONWebTokenError)
        self.assertIsNone(result.data["node"])

    def test_missing_user_is_refused(self):
        result = self._execute(None)

        self.assertIsNotNone(result.errors)
        self.assertIsInstance(result.errors[0].original_error, JSONWebTokenError)
        self.assertIsNone(result.data["node"])

    def test_authenticated_caller_reaches_the_node(self):
        result = self._execute(self.user)

        self.assertIsNone(result.errors)
        self.assertEqual("NodeFieldRole", result.data["node"]["name"])
