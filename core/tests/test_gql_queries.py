import json

from django.test import TestCase, override_settings
from graphql_relay import to_global_id

from core.apps import CoreConfig
from core.gql.max_length_constraints import build_max_length_constraints
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.test_helpers import create_test_interactive_user, create_test_role

try:
    from insuree.models import Insuree
except ImportError:
    Insuree = None


class MaxLengthConstraintsTestCase(TestCase):
    def test_build_max_length_constraints_returns_supported_admin_user_fields(self):
        constraints = build_max_length_constraints()

        self.assertIn("admin", constraints)
        self.assertIn("user", constraints["admin"])
        self.assertEqual(
            constraints["admin"]["user"],
            {
                "username": 50,
                "lastName": 100,
                "otherNames": 100,
                "phone": 50,
                "email": 200,
            },
        )

    def test_build_max_length_constraints_excludes_uncontrolled_models(self):
        constraints = build_max_length_constraints()

        self.assertNotIn("logentry", constraints)
        self.assertNotIn("session", constraints)
        self.assertNotIn("historicalinteractiveuser", constraints)

    def test_build_max_length_constraints_returns_insuree_fields_when_available(self):
        if not Insuree:
            self.skipTest("Insuree module is not installed")

        constraints = build_max_length_constraints()

        self.assertIn("insuree", constraints)
        self.assertIn("insuree", constraints["insuree"])
        self.assertEqual(
            constraints["insuree"]["insuree"],
            {
                "uuid": 36,
                "chfId": 50,
                "lastName": 100,
                "otherNames": 100,
                "marital": 1,
                "passport": 25,
                "phone": 50,
                "email": 100,
                "currentAddress": 200,
                "geolocation": 250,
                "status": 2,
            },
        )


@override_settings(ROW_SECURITY=False)
class InteractiveUserNodeAuthzTests(openIMISGraphQLTestCase):
    """Regression for the roles/districts authZ downgrade, simulating the real
    attack rather than calling resolvers with a mocked info.

    InteractiveUserGQLType implements relay.Node, so its roles/districts are
    reachable through the global `node(id)` query — which is not behind the
    `users` connection's permission gate. An authenticated user with no rights
    should not be able to read another user's roles/districts by enumerating
    global IDs. ROW_SECURITY is disabled because otherwise
    InteractiveUser.get_queryset raises before the field resolver runs.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.target = create_test_interactive_user(
            username="node_target",
            roles=[create_test_role(name="NodeTargetRole", perm_names=["gql_query_users_perms"]).id],
        )
        # Authenticated, no rights — would have passed the old is_authenticated check.
        cls.attacker = create_test_interactive_user(
            username="node_attacker",
            roles=[create_test_role(name="NodeAttackerRole", perm_names=[]).id],
        )
        # Holds the users permission (as the admin Users pages require).
        cls.privileged = create_test_interactive_user(
            username="node_privileged",
            roles=[create_test_role(name="NodeUsersRole", perm_names=["gql_query_users_perms"]).id],
        )
        cls.target_gid = to_global_id("InteractiveUserGQLType", cls.target.i_user.id)

    def _node(self, user, selection):
        query = (
            "query ($id: ID!) { node(id: $id) { "
            "... on InteractiveUserGQLType { %s } } }" % selection
        )
        resp = self.query(
            query,
            variables={"id": self.target_gid},
            headers={"HTTP_AUTHORIZATION": f"Bearer {BaseTestContext(user=user).get_jwt()}"},
        )
        return json.loads(resp.content)

    @staticmethod
    def _is_unauthorized(content):
        return any(e.get("message") == "unauthorized" for e in content.get("errors", []))

    @staticmethod
    def _node_field(content, field):
        # A denied non-null field can null the whole `node` via GraphQL
        # null-propagation, so read defensively.
        node = (content.get("data") or {}).get("node")
        return node.get(field) if node else None

    def test_node_roles_denied_without_users_permission(self):
        self.assertFalse(self.attacker.has_perms(CoreConfig.gql_query_users_perms))
        content = self._node(self.attacker, "roles { id name }")
        self.assertTrue(self._is_unauthorized(content))
        self.assertIsNone(self._node_field(content, "roles"))

    def test_node_districts_denied_without_users_permission(self):
        content = self._node(self.attacker, "userdistrictSet { location { id } }")
        self.assertTrue(self._is_unauthorized(content))
        self.assertIsNone(self._node_field(content, "userdistrictSet"))

    def test_node_roles_allowed_with_users_permission(self):
        content = self._node(self.privileged, "roles { id name }")
        self.assertFalse(self._is_unauthorized(content))
        self.assertIsInstance(self._node_field(content, "roles"), list)