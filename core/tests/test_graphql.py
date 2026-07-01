from core.models.openimis_graphql_test_case import (
    openIMISGraphQLTestCase,
    BaseTestContext,
)
from core.models import Language, User
from core.test_helpers import create_test_interactive_user, create_admin_role
from core.user_types import UT_OFFICER, UT_CLAIM_ADMIN, UT_INTERACTIVE
from location.models import Location
from location.test_helpers import create_test_health_facility, create_test_village
import json
import uuid


class gqlTest(openIMISGraphQLTestCase):
    admin_user = None
    admin_username = "Adminlogin"
    admin_password = "EdfmD3!12@#"
    district = None
    test_hf = None
    test_village = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(
            username=cls.admin_username, password=cls.admin_password
        )
        cls.admin_token_context = BaseTestContext(user=cls.admin_user)
        cls.admin_token = cls.admin_token_context.get_jwt()
        cls.disctict = Location.objects.filter(type="D", *Location.filter_validity()).first()

        # Create test objects for Officer / ClaimAdmin linked user tests
        cls.test_hf = create_test_health_facility()
        cls.test_village = create_test_village()

        # Create French language if it doesn't exist
        Language.objects.get_or_create(
            code="fr",
            defaults={"name": "Français", "sort_order": 1}
        )
        Language.objects.get_or_create(
            code="en",
            defaults={"name": "English", "sort_order": 2}
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
        query = f"""
            mutation {{
            changeUserLanguage(
                input: {{clientMutationId: "{str(uuid.uuid4())}",
                clientMutationLabel: "Change User Language",
                languageId: "fr"}}
            ) {{
                clientMutationId
                internalId
            }}
            }}

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
                "userTypes": [UT_INTERACTIVE],
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

    # --- Helper for User + usertype GQL tests ---
    def _create_user_gql(self, input_data):
        """Create a user (with possible Officer/ClaimAdmin links) via GQL and wait for mutation."""
        if "clientMutationId" not in input_data or not input_data.get("clientMutationId"):
            input_data["clientMutationId"] = str(uuid.uuid4())
        cmid = input_data["clientMutationId"]

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
        variables = {"input": input_data}
        response = self.query(
            query,
            variables=variables,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
        )
        self.assertResponseNoErrors(response)
        self.get_mutation_result(cmid, self.admin_token)
        return cmid

    def _query_user(self, username):
        """Fetch a user node via GQL users query. Returns the node dict or None."""
        query = """
            query ($username: String!) {
                users(username: $username, first: 1) {
                    edges {
                        node {
                            id
                            username
                            userTypes
                            lastName
                            otherNames
                            email
                            phone
                        }
                    }
                }
            }
        """
        response = self.query(
            query,
            variables={"username": username},
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
        )
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        edges = content.get("data", {}).get("users", {}).get("edges", [])
        return edges[0]["node"] if edges else None

    def _update_user_gql(self, input_data):
        """Update a user via GQL and wait."""
        if "clientMutationId" not in input_data or not input_data.get("clientMutationId"):
            input_data["clientMutationId"] = str(uuid.uuid4())
        cmid = input_data["clientMutationId"]

        query = """
            mutation (
                $input: UpdateUserMutationInput!
            ){
                updateUser(input: $input)
                {
                    clientMutationId
                    internalId
                }
            }
        """
        variables = {"input": input_data}
        response = self.query(
            query,
            variables=variables,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
        )
        self.assertResponseNoErrors(response)
        self.get_mutation_result(cmid, self.admin_token)
        return cmid

    # --- GQL tests for User with Officer / ClaimAdministrator (usertypes) ---

    def test_create_user_with_officer_usertype(self):
        """Create User linked to Officer via usertypes."""
        username = "TSTEO01" + str(uuid.uuid4())[:4]
        input_data = {
            "username": username,
            "userTypes": [UT_OFFICER],
            "lastName": "Enrollment",
            "otherNames": "Officer01",
            "email": "eo01@test.openimis.org",
            "phone": "+123456789",
            "language": "en",
            "healthFacilityId": self.test_hf.id,
            "clientMutationLabel": "Create officer user",
        }
        self._create_user_gql(input_data)

        # Verify via GQL read
        node = self._query_user(username)
        self.assertIsNotNone(node, "Created officer-linked user should be queryable")
        self.assertEqual(node["username"], username)
        self.assertEqual(node["userTypes"], [UT_OFFICER])
        self.assertEqual(node["lastName"], "Enrollment")
        self.assertEqual(node["otherNames"], "Officer01")

        # Verify via ORM + get_user_types
        db_user = User.objects.filter(username=username).first()
        self.assertIsNotNone(db_user)
        self.assertIsNotNone(db_user.officer)
        self.assertEqual(db_user.officer.last_name, "Enrollment")
        # Also test that userTypes resolver would return it (already checked via GQL)

    def test_create_user_with_claim_admin_usertype(self):
        """Create User linked to ClaimAdministrator via usertypes."""
        username = "TSTCA01" + str(uuid.uuid4())[:4]
        input_data = {
            "username": username,
            "userTypes": [UT_CLAIM_ADMIN],
            "lastName": "Claim",
            "otherNames": "Admin01",
            "email": "ca01@test.openimis.org",
            "phone": "+987654321",
            "language": "en",
            "healthFacilityId": self.test_hf.id,
            "clientMutationLabel": "Create claim admin user",
        }
        self._create_user_gql(input_data)

        node = self._query_user(username)
        self.assertIsNotNone(node)
        self.assertEqual(node["username"], username)
        self.assertEqual(node["userTypes"], [UT_CLAIM_ADMIN])
        self.assertEqual(node["lastName"], "Claim")
        self.assertEqual(node["otherNames"], "Admin01")

        db_user = User.objects.filter(username=username).first()
        self.assertIsNotNone(db_user)
        self.assertIsNotNone(db_user.claim_admin)
        self.assertEqual(db_user.claim_admin.last_name, "Claim")
        self.assertEqual(db_user.claim_admin.health_facility_id, self.test_hf.id)

    def test_create_user_with_interactive_and_claim_admin(self):
        """Create mixed user: INTERACTIVE + CLAIM_ADMIN (common real-world case)."""
        username = "TSTICCA" + str(uuid.uuid4())[:4]
        role_id = create_admin_role().id
        input_data = {
            "username": username,
            "userTypes": [UT_INTERACTIVE, UT_CLAIM_ADMIN],
            "lastName": "Mixed",
            "otherNames": "UserCA",
            "email": "mixca@test.openimis.org",
            "language": "en",
            "healthFacilityId": self.test_hf.id,
            "roles": [role_id],
            "districts": [self.disctict.id] if self.disctict else [],
            "password": "P@ssw0rdMixed123!",
            "clientMutationLabel": "Create interactive+claimadmin user",
        }
        self._create_user_gql(input_data)

        node = self._query_user(username)
        self.assertIsNotNone(node)
        # Order is not guaranteed; use set compare
        self.assertCountEqual(node["userTypes"], [UT_INTERACTIVE, UT_CLAIM_ADMIN])
        self.assertEqual(node["lastName"], "Mixed")

        db_user = User.objects.filter(username=username).first()
        self.assertIsNotNone(db_user.i_user)
        self.assertIsNotNone(db_user.claim_admin)
        self.assertIsNone(db_user.officer)

    def test_query_users_with_user_types_filter_and_read_links(self):
        """Reading users with usertype filter and confirming linked class data via userTypes."""
        # Create dedicated users for this test (cross-test data not visible due to transaction rollbacks)
        off_username = "TSTEOF" + str(uuid.uuid4())[:4]
        self._create_user_gql({
            "username": off_username,
            "userTypes": [UT_OFFICER],
            "lastName": "FilterOff",
            "otherNames": "EO",
            "email": "filteroff@test.com",
            "language": "en",
            "healthFacilityId": self.test_hf.id,
        })

        ca_username = "TSTCAF" + str(uuid.uuid4())[:4]
        self._create_user_gql({
            "username": ca_username,
            "userTypes": [UT_CLAIM_ADMIN],
            "lastName": "FilterCA",
            "otherNames": "CA",
            "email": "filterca@test.com",
            "language": "en",
            "healthFacilityId": self.test_hf.id,
        })

        # Filter by user type OFFICER
        query = f"""
            query {{
                users(userTypes: [{UT_OFFICER}], first: 5) {{
                    edges {{
                        node {{
                            username
                            userTypes
                        }}
                    }}
                }}
            }}
        """
        response = self.query(
            query, headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        usernames = [e["node"]["username"] for e in content["data"]["users"]["edges"]]
        types_lists = [e["node"]["userTypes"] for e in content["data"]["users"]["edges"]]
        self.assertIn(off_username, usernames)
        # At least one should have OFFICER in its types
        self.assertTrue(any(UT_OFFICER in t for t in types_lists))

        # Also verify claim via direct fetch
        ca_node = self._query_user(ca_username)
        self.assertIsNotNone(ca_node)
        self.assertIn(UT_CLAIM_ADMIN, ca_node["userTypes"])

    def test_update_user_adds_officer_link_via_usertypes(self):
        """Update an existing (interactive) user to also link an Officer by changing userTypes."""
        # First create a simple interactive user
        int_username = "TSTINT1" + str(uuid.uuid4())[:4]
        role_id = create_admin_role().id
        self._create_user_gql({
            "username": int_username,
            "userTypes": [UT_INTERACTIVE],
            "lastName": "Interactive",
            "otherNames": "Only",
            "email": "int1@test.com",
            "language": "en",
            "roles": [role_id],
            "districts": [self.disctict.id] if self.disctict else [],
            "password": "P@ss4IntUser!",
        })

        # Get its PK (used as 'uuid' in update mutation input)
        db_user = User.objects.get(username=int_username)
        user_pk = str(db_user.id)

        # Now update it to also be OFFICER (add usertype + required officer fields)
        update_input = {
            "uuid": user_pk,
            "username": int_username,
            "userTypes": [UT_INTERACTIVE, UT_OFFICER],
            "lastName": "InteractivePlusOff",
            "otherNames": "Upgraded",
            "email": "int1@test.com",
            "language": "en",
            "healthFacilityId": self.test_hf.id,
            "roles": [role_id],
            "districts": [self.disctict.id] if self.disctict else [],
            "clientMutationLabel": "Upgrade user to also be officer",
        }
        self._update_user_gql(update_input)

        # Verify via GQL
        node = self._query_user(int_username)
        self.assertIsNotNone(node)
        self.assertCountEqual(node.get("userTypes", []), [UT_INTERACTIVE, UT_OFFICER])
        self.assertEqual(node["lastName"], "InteractivePlusOff")

        # Verify links
        db_user.refresh_from_db()
        self.assertIsNotNone(db_user.i_user)
        self.assertIsNotNone(db_user.officer)
        self.assertIsNone(getattr(db_user, "claim_admin", None))

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
