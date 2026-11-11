import json

from core.models import InteractiveUser
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user, create_test_role


class InteractiveUsersQueryTest(openIMISGraphQLTestCase):
    """`interactiveUsers` must run its own resolver.

    graphene looks a resolver up by the attribute name as written. The field is
    declared `interactiveUsers`, so a method named `resolve_interactive_users` is
    never called: the users right was not checked and deleted users and history
    copies were listed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = create_test_interactive_user(username="iuQueryAdmin")
        cls.admin_token = cls.get_jwt_token(cls.admin)
        no_right_role = create_test_role(perm_names=[], name="iuQuery-no-users-right")
        cls.no_right = create_test_interactive_user(
            username="iuQueryNoRight", roles=[no_right_role.id])
        cls.no_right_token = cls.get_jwt_token(cls.no_right)
        create_test_interactive_user(username="iuQueryLive", custom_props={"last_name": "IuQueryProbe"})
        deleted = create_test_interactive_user(
            username="iuQueryDeleted", custom_props={"last_name": "IuQueryProbe"})
        InteractiveUser.objects.filter(id=deleted.i_user.id).update(validity_to="2020-01-01")

    def _query(self, token, args=""):
        return self.query(
            '{ interactiveUsers(lastName_Icontains: "IuQueryProbe"%s) '
            '{ edges { node { loginName } } } }' % args,
            headers={"HTTP_AUTHORIZATION": f"Bearer {token}"})

    def _logins(self, args=""):
        response = self._query(self.admin_token, args)
        self.assertResponseNoErrors(response)
        edges = json.loads(response.content)["data"]["interactiveUsers"]["edges"]
        return sorted(edge["node"]["loginName"] for edge in edges)

    def test_the_users_right_is_checked(self):
        content = json.loads(self._query(self.no_right_token).content)
        self.assertTrue(content.get("errors"))
        self.assertIsNone((content.get("data") or {}).get("interactiveUsers"))

    def test_deleted_users_are_hidden(self):
        self.assertEqual(["iuQueryLive"], self._logins())

    def test_show_history_lists_deleted_users(self):
        self.assertEqual(["iuQueryDeleted", "iuQueryLive"], self._logins(", showHistory: true"))

    def _node_login(self, token, i_user):
        from graphql_relay import to_global_id
        response = self.query(
            '{ node(id: "%s") { ... on InteractiveUserGQLType { loginName } } }'
            % to_global_id("InteractiveUserGQLType", i_user.id),
            headers={"HTTP_AUTHORIZATION": f"Bearer {token}"})
        content = json.loads(response.content)
        return ((content.get("data") or {}).get("node") or {}).get("loginName")

    def test_node_hides_other_users_without_the_users_right(self):
        # OP-3124: node(id) must not expose another user's record (PII)
        self.assertIsNone(self._node_login(self.no_right_token, self.admin.i_user))
        self.assertEqual("iuQueryNoRight", self._node_login(self.no_right_token, self.no_right.i_user))
        self.assertEqual("iuQueryNoRight", self._node_login(self.admin_token, self.no_right.i_user))
