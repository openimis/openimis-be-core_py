from core.rights_role_test_case import RightsRoleGraphQLTestCase
from core.test_helpers import (
    create_hf_admin_role,
    create_right_only_user,
    create_role_user,
)
from location.test_helpers import create_basic_test_locations


USERS_QUERY = """
query {
  users(first: 5) {
    edges { node { username } }
  }
}
"""


class UserRightsTests(RightsRoleGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_basic_test_locations()

    def test_query_users_right(self):
        allowed = create_right_only_user(
            "r_usr_q", ["gql_query_users_perms"], district_codes=self.DISTRICT_CODES
        )
        denied = create_right_only_user("r_usr_q_no", [], district_codes=self.DISTRICT_CODES)
        self.assert_user_has_named_perms(allowed, ["gql_query_users_perms"])
        self.assert_user_lacks_named_perms(denied, ["gql_query_users_perms"])
        self.assert_gql_unauthorized(denied, USERS_QUERY)

    def test_user_mutation_rights_assigned(self):
        allowed = create_right_only_user(
            "r_usr_m",
            [
                "gql_mutation_create_users_perms",
                "gql_mutation_update_users_perms",
                "gql_mutation_delete_users_perms",
            ],
            district_codes=self.DISTRICT_CODES,
        )
        denied = create_right_only_user("r_usr_m_no", [], district_codes=self.DISTRICT_CODES)
        for perm in (
            "gql_mutation_create_users_perms",
            "gql_mutation_update_users_perms",
            "gql_mutation_delete_users_perms",
        ):
            self.assert_user_has_named_perms(allowed, [perm])
            self.assert_user_lacks_named_perms(denied, [perm])
        self.assert_user_lacks_named_perms(denied, ["gql_mutation_create_users_perms"])


class UserRoleTests(RightsRoleGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_basic_test_locations()
        cls.hf_admin = create_role_user(
            "usr_hf", create_hf_admin_role(), district_codes=cls.DISTRICT_CODES
        )

    def test_hf_admin_can_query_and_manage_users(self):
        self.assert_user_has_named_perms(self.hf_admin, ["gql_query_users_perms"])
        self.assert_user_has_named_perms(self.hf_admin, ["gql_mutation_create_users_perms"])
        self.assert_user_has_named_perms(self.hf_admin, ["gql_mutation_update_users_perms"])
        self.assert_user_has_named_perms(self.hf_admin, ["gql_mutation_delete_users_perms"])
        self.assert_gql_ok(self.hf_admin, USERS_QUERY)
