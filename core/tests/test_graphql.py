from core.models.openimis_graphql_test_case import (
    openIMISGraphQLTestCase,
    BaseTestContext,
)
from core.models import Language
from core.test_helpers import create_test_interactive_user, create_admin_role
from location.models import Location
import json


class gqlTest(openIMISGraphQLTestCase):
    admin_user = None
    admin_username = "Adminlogin"
    admin_password = "EdfmD3!12@#"
    district = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(
            username=cls.admin_username, password=cls.admin_password
        )
        cls.admin_token_context = BaseTestContext(user=cls.admin_user)
        cls.admin_token = cls.admin_token_context.get_jwt()
        cls.disctict = Location.objects.filter(type="D", *Location.filter_validity()).first()

        # Create French language if it doesn't exist
        Language.objects.get_or_create(
            code="fr",
            defaults={"name": "Français", "sort_order": 1}
        )

    def test_login_successful(self):
        variables = {
            "username": str(self.admin_username),
            "password": str(self.admin_password),
        }

        query = """
            mutation authenticate($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password)
                {
                refreshExpiresIn
                }
            }
        """
        response = self.query(query, variables=variables)
        self.assertResponseNoErrors(response)
        _ = json.loads(response.content)

    def test_login_default_successful(self):
        variables = {"username": "Admin", "password": "admin123"}

        query = """
            mutation authenticate($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password)
                {
                refreshExpiresIn
                }
            }
        """
        response = self.query(query, variables=variables)
        self.assertResponseNoErrors(response)
        _ = json.loads(response.content)

    def test_login_wrong_credentials(self):
        variables = {"username": str(self.admin_username), "password": "notright"}

        query = """
            mutation authenticate($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password)
                {
                refreshExpiresIn
                }
            }
        """
        response = self.query(query, variables=variables)
        self.assertResponseHasErrors(response)
        _ = json.loads(response.content)

    def test_login_wrong_credentials_prevents_user_enumeration(self):
        """Both wrong password and non-existent user should return identical error responses."""
        query = """
            mutation authenticate($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password)
                {
                refreshExpiresIn
                }
            }
        """
        wrong_password_response = self.query(
            query, variables={"username": str(self.admin_username), "password": "wrongpass"}
        )
        nonexistent_user_response = self.query(
            query, variables={"username": "nonexistent_user_xyz", "password": "anypass"}
        )

        wrong_password_data = json.loads(wrong_password_response.content)
        nonexistent_user_data = json.loads(nonexistent_user_response.content)

        self.assertEqual(wrong_password_response.status_code, nonexistent_user_response.status_code)
        self.assertEqual(
            wrong_password_data["errors"][0]["message"],
            nonexistent_user_data["errors"][0]["message"]
        )
        self.assertEqual(wrong_password_data["errors"][0]["message"], "INCORRECT_CREDENTIALS")

    def test_change_langue(self):
        query = """
            mutation {
            changeUserLanguage(
                input: {clientMutationId: "b2a639a9-1a85-4643-bf84-69d05160c8ee",
                clientMutationLabel: "Change User Language",
                languageId: "fr"}
            ) {
                clientMutationId
                internalId
            }
            }
        """
        self.send_mutation_raw(query, self.admin_token)

    def test_create_role(self):

        input_param = {
            "name": "SP Enrollment Officer",
            "isBlocked": False,
            "isSystem": False,
            "rightsId": [
                159001,
                159002,
                159003,
                159004,
                159005,
                180001,
                180002,
                180003,
                180004,
            ],
        }

        self.send_mutation("createRole", input_param, self.admin_token)

    def test_create_user_with_null_uuid(self):
        query = """
            mutation (
                $input: CreateUserMutationInput!
            ){
                createUser(input: $input)
                {
                    clientMutationId
                    internalId
                }
            }
        """
        variables = {
            "input": {
                "uuid": None,
                "username": "OCM-176",
                "userTypes": ["INTERACTIVE"],
                "lastName": "add",
                "otherNames": "user",
                "email": "ocm-176@openimis.org",
                "password": "pOCM-176!OCM-176",
                "healthFacilityId": None,
                "districts": [self.disctict.id],
                "locationId": None,
                "language": "en",
                "roles": [create_admin_role().id],
                "substitutionOfficerId": None,
                "clientMutationLabel": "Create user",
                "clientMutationId": "95b431f3-0c12-40ad-bc01-51034702366d",
            }
        }
        response = self.query(
            query,
            variables=variables,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
        )
        self.assertResponseNoErrors(response)
        self.get_mutation_result(
            "95b431f3-0c12-40ad-bc01-51034702366d", self.admin_token
        )

    def test_user_district_query(self):
        query = """
    {
      userDistricts
      {
        id,uuid,code,name,parent{id, uuid, code, name}
      }
    }
    """
        response = self.query(
            query, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)

    def test_fetch_claimadmin(self):
        query = """
      query ClaimAdminPicker ($search: String, $hf: String, $region_uuid: String, $district_uuid: String) {
          claimAdmins(
              search: $search,
              first: 20,
              healthFacility_Uuid: $hf,
              regionUuid: $region_uuid,
              districtUuid: $district_uuid
          ) {
              edges {
                  node {
                      id
                      uuid
                      code
                      lastName
                      otherNames
                      healthFacility {
                          id uuid code name level
                          servicesPricelist{id, uuid}, itemsPricelist{id, uuid}
                          location {
                              id
                              uuid
                              code
                              name
                              parent {
                                code name id uuid
                              }
                          }
                      }
                    }
                }
            }
        }
        """
        response = self.query(
            query, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)

    def test_authority_picker(self):
        query = """
            query AuthorityPicker {
                modulesPermissions  {
                    modulePermsList {
                        moduleName
                        permissions {
                            permsName
                            permsValue
                        }
                    }
                }
            }
        """
        response = self.query(
            query, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)

    def test_users_query_returns_interactive_users(self):
        """Test that the users query returns users with interactive user links (i_user)."""
        query = """
            {
                users(first: 10, orderBy: ["username"]) {
                    totalCount
                    edges {
                        node {
                            id
                            username
                        }
                    }
                }
            }
        """
        response = self.query(
            query, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        users_data = content["data"]["users"]
        self.assertGreater(
            users_data["totalCount"],
            0,
            "Users query should return at least one user (the admin user)"
        )
        usernames = [edge["node"]["username"] for edge in users_data["edges"]]
        self.assertIn(
            self.admin_username,
            usernames,
            f"Admin user '{self.admin_username}' should be in the returned users"
        )

    def test_user_modification_creates_history_with_user(self):
        """Test that user modification via GraphQL creates history record with user included for audit"""
        # Get initial history count for the admin user
        initial_history_count = self.admin_user.i_user.history.count()

        # Change the user's language via GraphQL
        query = """
            mutation {
                changeUserLanguage(
                    input: {
                        clientMutationId: "test-history-audit",
                        clientMutationLabel: "Test User History Audit",
                        languageId: "fr"
                    }
                ) {
                    clientMutationId
                    internalId
                }
            }
        """
        response = self.query(
            query, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)

        # Check that history record was created
        final_history_count = self.admin_user.i_user.history.count()
        self.assertEqual(
            final_history_count,
            initial_history_count + 1,
            "History record should have been created for user modification"
        )

        # Get the latest history record
        latest_history = self.admin_user.i_user.history.latest('history_date')  # Ordered by -history_date, -history_id

        # Verify that the history record contains the user who made the change
        self.assertIsNotNone(
            latest_history.history_user,
            "History record should contain the user who made the change"
        )
        self.assertEqual(
            latest_history.history_user.id,
            self.admin_user.id,
            "History record should reference the correct user who made the change"
        )

        # Verify that the language was actually changed
        self.admin_user.i_user.refresh_from_db()
        self.assertEqual(
            self.admin_user.i_user.language.code,
            "fr",
            "User language should have been changed to French"
        )

    def test_validate_username_existing(self):
        # Test validateUsername with an existing username - should return False
        query = """
            query ($username: String!) {
                isValid: validateUsername(username: $username)
            }
        """
        variables = {"username": self.admin_username}
        response = self.query(query, variables=variables, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"})
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        self.assertFalse(content["data"]["isValid"])

    def test_validate_username_non_existing(self):
        # Test validateUsername with a non-existing username - should return True
        query = """
            query ($username: String!) {
                isValid: validateUsername(username: $username)
            }
        """
        variables = {"username": "nonexistingusername123"}
        response = self.query(query, variables=variables, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"})
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        self.assertTrue(content["data"]["isValid"])

    # def test_admin_user_is_superuser(self):
    #     # Test that the default "Admin" user has isSuperuser=True through GraphQL
    #     query = """
    #         query {
    #             users(username: "Admin") {
    #                 edges {
    #                     node {
    #                         username
    #                         isSuperuser
    #                     }
    #                 }
    #             }
    #         }
    #     """
    #     response = self.query(query, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"})
    #     self.assertResponseNoErrors(response)
    #     content = json.loads(response.content)
    #     users = content["data"]["users"]["edges"]
    #     self.assertEqual(len(users), 1, "Should find exactly one Admin user")
    #     admin_user = users[0]["node"]
    #     self.assertEqual(admin_user["username"], "Admin")
    #     self.assertTrue(admin_user["isSuperuser"], "Admin user should have isSuperuser=True")
