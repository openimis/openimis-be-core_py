import datetime
import json

from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.schema import update_or_create_role
from core.services.userServices import create_or_update_user_roles
from core.test_helpers import create_test_interactive_user, create_test_role

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
      auditUserName
      changeReason
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

    def _query(self, variables, authenticated=True, token=None):
        params = {}
        if authenticated:
            params["headers"] = {
                "HTTP_AUTHORIZATION": f"Bearer {token or self.admin_token}"
            }
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

    def test_change_log_reports_the_actor_by_name(self):
        content = self._query({"uuid": self.role.uuid})

        items = content["data"]["roleChangeLog"]["items"]
        grants = [i for i in items if i["changeType"] == "RIGHT_GRANTED"]
        self.assertEqual(
            grants[0]["auditUserName"], self.admin_user.i_user.login_name
        )

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

    def test_change_log_requires_the_roles_right(self):
        # 121701 (users) is a different right from 122001 (roles).
        role = create_test_role(
            perm_names=["gql_query_users_perms"],
            name="ChangeLogUsersOnly",
            is_system=0,
        )
        limited = create_test_interactive_user(
            username="RoleChangeLogNoRolesRight",
            password=self.admin_password,
            roles=[role.id],
        )
        token = BaseTestContext(user=limited).get_jwt()

        content = self._query({"uuid": self.role.uuid}, token=token)

        self.assertIsNotNone(content.get("errors"))
        self.assertIsNone(content.get("data", {}).get("roleChangeLog"))

    def test_first_zero_returns_an_empty_page(self):
        content = self._query({"uuid": self.role.uuid, "first": 0})["data"][
            "roleChangeLog"
        ]

        self.assertEqual(content["items"], [])
        self.assertGreater(content["totalCount"], 0)

    def test_negative_first_is_rejected(self):
        content = self._query({"uuid": self.role.uuid, "first": -1})

        self.assertIsNotNone(content.get("errors"))
        self.assertIn("negative_paging", json.dumps(content["errors"]))

    def test_negative_offset_is_rejected(self):
        content = self._query({"uuid": self.role.uuid, "offset": -1})

        self.assertIsNotNone(content.get("errors"))
        self.assertIn("negative_paging", json.dumps(content["errors"]))

    def _assign_admin_to_the_role(self):
        create_or_update_user_roles(
            self.admin_user.i_user, [self.role.id], self.admin_user.i_user.id
        )

    def test_logins_are_hidden_from_callers_without_the_users_right(self):
        # 122001 (roles) without 121701 (users): the timeline stays readable,
        # the identities do not.
        self._assign_admin_to_the_role()
        role = create_test_role(
            perm_names=["gql_query_roles_perms"],
            name="ChangeLogRolesOnly",
            is_system=0,
        )
        limited = create_test_interactive_user(
            username="RoleChangeLogRolesOnly",
            password=self.admin_password,
            roles=[role.id],
        )
        token = BaseTestContext(user=limited).get_jwt()

        items = self._query({"uuid": self.role.uuid}, token=token)["data"][
            "roleChangeLog"
        ]["items"]

        self.assertTrue(items)
        self.assertTrue(all(i["auditUserName"] is None for i in items))
        assignments = [i for i in items if i["changeType"] == "USER_ASSIGNED"]
        self.assertTrue(assignments)
        self.assertTrue(all(i["newValue"].startswith("#") for i in assignments))

    def test_logins_are_visible_with_the_users_right(self):
        self._assign_admin_to_the_role()

        items = self._query({"uuid": self.role.uuid})["data"]["roleChangeLog"][
            "items"
        ]

        assignments = [i for i in items if i["changeType"] == "USER_ASSIGNED"]
        self.assertIn(
            self.admin_user.i_user.login_name, {i["newValue"] for i in assignments}
        )

    def test_change_log_exposes_the_change_reason(self):
        content = self._query({"uuid": self.role.uuid})
        items = content["data"]["roleChangeLog"]["items"]

        renamed = next(i for i in items if i["changeType"] == "ATTRIBUTE_CHANGED")
        self.assertEqual(renamed["changeReason"], "ATTRIBUTE_CHANGED")
        granted = next(i for i in items if i["changeType"] == "RIGHT_GRANTED")
        self.assertEqual(granted["changeReason"], "RIGHT_GRANTED")
