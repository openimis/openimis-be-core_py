import json

from django.test import TestCase

from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.models import User
from core.test_helpers import create_test_interactive_user, create_test_officer
from core.user_types import UT_INTERACTIVE, UT_OFFICER, UT_CLAIM_ADMIN, get_user_types


class GetUserTypesTest(TestCase):
    def test_interactive_user_has_interactive_type(self):
        user = create_test_interactive_user(username="ut_interactive")
        self.assertEqual(get_user_types(user), [UT_INTERACTIVE])

    def test_officer_user_has_officer_type(self):
        officer = create_test_officer(custom_props={"code": "UTEO01", "last_name": "Off", "other_names": "Test"})
        core_user = User.objects.create(username=officer.code, officer=officer)
        self.assertEqual(get_user_types(core_user), [UT_OFFICER])

    def test_claim_admin_user_has_claim_admin_type(self):
        try:
            from claim.test_helpers import create_test_claim_admin
            from location.test_helpers import create_test_health_facility
            hf = create_test_health_facility()
            ca = create_test_claim_admin(custom_props={"code": "UTCA01", "last_name": "CA", "other_names": "Test", "health_facility_id": hf.id})
        except Exception:
            self.skipTest("claim module or HF not available for test")
        core_user = User.objects.create(username=ca.code, claim_admin=ca)
        self.assertEqual(get_user_types(core_user), [UT_CLAIM_ADMIN])

    def test_mixed_user_types(self):
        # interactive + officer
        core_user = create_test_interactive_user(username="ut_mixed")
        officer = create_test_officer(custom_props={"code": "UTEO02"})
        core_user.officer = officer
        core_user.save(silent=True)
        types = get_user_types(core_user)
        self.assertIn(UT_INTERACTIVE, types)
        self.assertIn(UT_OFFICER, types)


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
