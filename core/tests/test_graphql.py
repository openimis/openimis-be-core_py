from core.models.openimis_graphql_test_case import (
    openIMISGraphQLTestCase,
    BaseTestContext,
)
from core.test_helpers import create_test_interactive_user
from core import filter_validity
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
        cls.disctict = Location.objects.filter(type="D", *filter_validity()).first()

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
                "roles": ["4"],
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
