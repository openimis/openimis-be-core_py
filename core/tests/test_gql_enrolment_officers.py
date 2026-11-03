"""enrolmentOfficers(str:) - the text search behind the enrolment officer picker."""

import json

from core.models import User
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.test_helpers import create_test_interactive_user, create_test_officer


class EnrolmentOfficerSearchTests(openIMISGraphQLTestCase):
    QUERY = "query ($str: String) { enrolmentOfficers(str: $str) { edges { node { code } } } }"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = create_test_interactive_user(username="eo_search_admin")
        cls.officer = create_test_officer(
            custom_props={"code": "EOSRCH1", "last_name": "Fairbrook", "other_names": "Ada"}
        )
        # A login name that shares nothing with the officer's code or names. Two
        # logins on one officer is what a join on the user table would duplicate.
        for username in ("ada.login.one", "ada.login.two"):
            login = create_test_interactive_user(username=username)
            User.objects.filter(id=login.id).update(officer=cls.officer)

    def _codes(self, search):
        resp = self.query(
            self.QUERY,
            variables={"str": search},
            headers={"HTTP_AUTHORIZATION": f"Bearer {BaseTestContext(user=self.admin).get_jwt()}"},
        )
        content = json.loads(resp.content)
        self.assertNotIn("errors", content, content.get("errors"))
        return [edge["node"]["code"] for edge in content["data"]["enrolmentOfficers"]["edges"]]

    def test_finds_an_officer_by_the_username_of_its_login(self):
        self.assertEqual(self._codes("ada.login"), ["EOSRCH1"])

    def test_an_officer_with_several_logins_is_listed_once(self):
        self.assertEqual(self._codes("EOSRCH1"), ["EOSRCH1"])
        self.assertEqual(self._codes("ada.login.t"), ["EOSRCH1"])

    def test_still_finds_an_officer_by_code_and_names(self):
        for search in ("EOSRCH", "Fairbrook", "Ada"):
            with self.subTest(search=search):
                self.assertEqual(self._codes(search), ["EOSRCH1"])
