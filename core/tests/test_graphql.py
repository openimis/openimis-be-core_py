from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from graphql_jwt.shortcuts import get_token
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
        cls.admin_user = create_test_interactive_user(username=cls.admin_username, password=cls.admin_password)
        cls.admin_token = get_token(cls.admin_user, cls.BaseTestContext(user=cls.admin_user))
        cls.disctict = Location.objects.filter(type='D', *filter_validity()).first()
    
    def test_login_successful(self):
        variables = {
            "username": str(self.admin_username),
            "password": str(self.admin_password)
        }

        query = """
            mutation authenticate($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password)
                {
                refreshExpiresIn
                }
            }
        """
        response = self.query(
            query,
            variables=variables
        )
        self.assertResponseNoErrors(response)
        _ = json.loads(response.content)

    def test_login_default_successful(self):
        variables = {
            "username": "Admin",
            "password": "admin123"
        }

        query = """
            mutation authenticate($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password)
                {
                refreshExpiresIn
                }
            }
        """
        response = self.query(
            query,
            variables=variables
        )
        self.assertResponseNoErrors(response)
        _ = json.loads(response.content)

    def test_login_wrong_credentials(self):
        variables = {
            "username": str(self.admin_username),
            "password": "notright"
        }

        query = """
            mutation authenticate($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password)
                {
                refreshExpiresIn
                }
            }
        """
        response = self.query(
            query,
            variables=variables
        )
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
        response = self.query(
            query,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)
        _ = json.loads(response.content)

    def test_create_role(self):
        query = """
            mutation {
                createRole(
                    input: {
                        name: "SP Enrollment Officer",
                        isBlocked: false,
                        isSystem: false,
                        rightsId: [159001,159002,159003,159004,159005,180001,180002,180003,180004]
                    }
                ) {
                    clientMutationId
                }
            }
        """
        response = self.query(
            query,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)

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
                "userTypes": [
                    "INTERACTIVE"
                ],
                "lastName": "add",
                "otherNames": "user",
                "email": "ocm-176@openimis.org",
                "password": "pOCM-176!OCM-176",
                "healthFacilityId": None,
                "districts": [
                    self.disctict.id
                ],
                "locationId": None,
                "language": "en",
                "roles": [
                    "4"
                ],
                "substitutionOfficerId": None,
                "clientMutationLabel": "Create user",
                "clientMutationId": "95b431f3-0c12-40ad-bc01-51034702366d"
            }
        }
        response = self.query(
            query,
            variables=variables,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)
        self.get_mutation_result("95b431f3-0c12-40ad-bc01-51034702366d", self.admin_token)
    
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
            query,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        )
        self.assertResponseNoErrors(response)