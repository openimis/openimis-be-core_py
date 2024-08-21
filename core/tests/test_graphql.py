from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from graphql_jwt.shortcuts import get_token

import json


class gqlTest(openIMISGraphQLTestCase):
    admin_user = None
    admin_username = "Adminlogin"
    admin_password = "EdfmD3!12@#"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(username=cls.admin_username, password=cls.admin_password)
        cls.admin_token = get_token(cls.admin_user, cls.BaseTestContext(user=cls.admin_user))

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
        content = json.loads(response.content)

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
        content = json.loads(response.content)

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
        content = json.loads(response.content)

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
        content = json.loads(response.content)
