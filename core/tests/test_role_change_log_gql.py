import datetime
import json

from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.schema import update_or_create_role
from core.test_helpers import create_test_interactive_user

_RIGHT_A = 121901
_RIGHT_B = 121902

_QUERY = """
query ($uuid: String!, $first: Int, $offset: Int) {
  roleChangeLog(roleUuid: $uuid, first: $first, offset: $offset) {
    totalCount
    items {
      timestamp
      changeType
      field
      oldValue
      newValue
      auditUserId
    }
  }
}
"""


class RoleChangeLogGQLTest(openIMISGraphQLTestCase):
    admin_username = "RoleChangeLogGQLAdmin"
    admin_password = "EdfmD3!12@#"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(
            username=cls.admin_username, password=cls.admin_password
        )
        cls.admin_token = BaseTestContext(user=cls.admin_user).get_jwt()

    def setUp(self):
        super().setUp()
        self.role = update_or_create_role(
            {
                "name": "GQLChangeLogRole",
                "is_system": 0,
                "is_blocked": False,
                "audit_user_id": self.admin_user.i_user.id,
                "validity_from": datetime.datetime.now(),
                "rights_id": [_RIGHT_A, _RIGHT_B],
            },
            self.admin_user,
        )
        update_or_create_role(
            {"uuid": self.role.uuid, "name": "GQLRenamedRole"}, self.admin_user
        )

    def _query(self, variables, authenticated=True):
        params = {}
        if authenticated:
            params["headers"] = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        response = self.query(_QUERY, variables=variables, **params)
        return json.loads(response.content)

    def test_change_log_reports_the_rename(self):
        content = self._query({"uuid": self.role.uuid})

        items = content["data"]["roleChangeLog"]["items"]
        renames = [
            i
            for i in items
            if i["changeType"] == "ATTRIBUTE_CHANGED" and i["field"] == "name"
        ]
        self.assertEqual(len(renames), 1)
        self.assertEqual(renames[0]["oldValue"], "GQLChangeLogRole")
        self.assertEqual(renames[0]["newValue"], "GQLRenamedRole")

    def test_change_log_requires_authentication(self):
        content = self._query({"uuid": self.role.uuid}, authenticated=False)

        self.assertIsNotNone(content.get("errors"))

    def test_unknown_role_uuid_returns_an_error(self):
        content = self._query({"uuid": "00000000-0000-0000-0000-000000000000"})

        self.assertIsNotNone(content.get("errors"))
        self.assertIn(
            "role_change_log",
            json.dumps(content["errors"]),
        )

    def test_first_limits_items_without_changing_total_count(self):
        unpaged = self._query({"uuid": self.role.uuid})["data"]["roleChangeLog"]

        paged = self._query({"uuid": self.role.uuid, "first": 2})["data"][
            "roleChangeLog"
        ]

        self.assertGreater(unpaged["totalCount"], 2)
        self.assertEqual(len(paged["items"]), 2)
        self.assertEqual(paged["totalCount"], unpaged["totalCount"])

    def test_offset_skips_entries(self):
        unpaged = self._query({"uuid": self.role.uuid})["data"]["roleChangeLog"]

        offset = self._query({"uuid": self.role.uuid, "offset": 1})["data"][
            "roleChangeLog"
        ]

        self.assertEqual(
            len(offset["items"]), len(unpaged["items"]) - 1
        )
        self.assertEqual(offset["items"][0], unpaged["items"][1])
