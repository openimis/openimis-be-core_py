import json

from django.test import TestCase

from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from core.user_types import UT_INTERACTIVE, get_user_types


class GetUserTypesTest(TestCase):
    def test_interactive_user_has_interactive_type(self):
        user = create_test_interactive_user(username="ut_interactive")
        self.assertEqual(get_user_types(user), [UT_INTERACTIVE])


class UserTypesGraphQLTest(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(username="ut_graphql_admin")
        cls.admin_token = cls.get_jwt_token(cls.admin_user)
        cls.admin_username = cls.admin_user.username

    def test_users_query_returns_user_types(self):
        query = """
            {
                users(username: "%s", first: 1) {
                    edges {
                        node {
                            username
                            userTypes
                        }
                    }
                }
            }
        """ % self.admin_username
        response = self.query(
            query, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        user_node = content["data"]["users"]["edges"][0]["node"]
        self.assertEqual(user_node["username"], self.admin_username)
        self.assertEqual(user_node["userTypes"], [UT_INTERACTIVE])
