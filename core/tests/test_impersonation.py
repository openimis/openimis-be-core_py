import json
from django.test import TestCase
from graphene_django.utils.testing import GraphQLTestCase
from graphql_jwt.shortcuts import get_token
from core.models import User, Role, InteractiveUser
from core.test_helpers import create_test_role, create_test_interactive_user
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.schema import CreateUserMutation

class ImpersonationTest(openIMISGraphQLTestCase):
    def setUp(self):
        super().setUp()
        # Create superadmin
        self.superadmin = User.objects.create_superuser(
            username="superadmin",
            email="superadmin@test.com",
            password="password",
            last_name="test",
            other_names="test"
        )
        # Create read-only role for users and roles
        read_role = create_test_role(perm_names=["gql_query_users_perms", "gql_query_roles_perms"], name="ReadOnlyUserRole")
        # Create regular user with read-only role
        self.regular_user = create_test_interactive_user(username="regular", email="regular@test.com", password="password", roles=[read_role.id])
        self.regular_interactive = self.regular_user.i_user
        # Create user without rights
        self.no_rights_user = create_test_interactive_user(username="no_rights", email="no_rights@test.com", password="password", roles=[])
        self.no_rights_interactive = self.no_rights_user.i_user
        # Invalid UUID
        self.invalid_uuid = "00000000-0000-0000-0000-000000000000"

    def test_impersonation_success(self):
        # Superadmin impersonates regular user to update their own profile or something
        # But since regular user may not have rights, but the task is to test invalid impersonation
        # Perhaps the mutation is to update another user
        # For simplicity, use a mutation that requires permission, like updating a user
        # Assume the mutation is createOrUpdateInteractiveUser
        token = get_token(self.superadmin)
        # Impersonate regular user, but since regular user may not have rights, but the test is for invalid
        # The task: "using a { 'X-Impersonate-User': uuid } that does not have such right"
        # So, impersonate a user that doesn't have the right for the mutation
        # So, the mutation should fail because the impersonated user doesn't have the right
        # For success, perhaps impersonate a user that does have the right, but since it's superadmin, it's to test the mechanism
        # But the test is for failure case
        # So, test that when impersonating a user without rights, the mutation fails
        query = """
            mutation ($input: UpdateUserMutationInput!) {
            updateUser(input: $input) {
                clientMutationId
                internalId
            }
        }
        """
        variables = {
            "input": {
                **self._instance_to_gql_input(self.regular_user, CreateUserMutation.Input, ['password']),
                **self._instance_to_gql_input(self.regular_interactive, CreateUserMutation.Input, ['password']),
                "lastName": "update",
                "clientMutationId": "test"
            }
        }
        # First, without impersonation, superadmin can do it
        response = self.query(
            mutation,
            variables=variables,
            headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
        )
        self.assertResponseNoErrors(response)
        # Now, impersonate no_rights_user, who doesn't have the right, so should fail
        response = self.query(
            query,
            variables=variables,
            headers={
                "HTTP_AUTHORIZATION": f"Bearer {token}",
                "HTTP_X_IMPERSONATE_USER": str(self.no_rights_user.uuid)
            }
        )
        # Should have errors, permission denied
        self.assertTrue(response.json().get("errors"))

    def test_invalid_impersonation_uuid(self):
        token = get_token(self.superadmin)
        
        query = """
            mutation ($input: UpdateUserMutationInput!) {
            updateUser(input: $input) {
                clientMutationId
                internalId
            }
        }
        """
        variables = {
            "input": {
                **self._instance_to_gql_input(self.regular_user, CreateUserMutation.Input, ['password']),
                **self._instance_to_gql_input(self.regular_interactive, CreateUserMutation.Input, ['password']),
                "lastName": "update",
                "clientMutationId": "test2"
                
            }
        }
        response = self.query(
            query,
            variables=variables,
            headers={
                "HTTP_AUTHORIZATION": f"Bearer {token}",
                "HTTP_X_IMPERSONATE_USER": self.invalid_uuid
            }
        )
        # Should have auth error
        self.assertEqual(response.status_code, 401)

    def test_non_superuser_impersonation(self):
        token = get_token(self.regular_user)
        query = """
            mutation ($input: UpdateUserMutationInput!) {
            updateUser(input: $input) {
                clientMutationId
                internalId
            }
        }
        """
        variables = {
            "input": {
                **self._instance_to_gql_input(self.regular_user, CreateUserMutation.Input, ['password']),
                **self._instance_to_gql_input(self.regular_interactive, CreateUserMutation.Input, ['password']),
                "lastName": "update",
                "clientMutationId": "test3"
            }
        }

        response = self.query(
            query,
            variables=variables,
            headers={
                "HTTP_AUTHORIZATION": f"Bearer {token}",
                "HTTP_X_IMPERSONATE_USER": str(self.no_rights_user.uuid)
            }
        )
        # Should have auth error
        self.assertEqual(response.status_code, 401)