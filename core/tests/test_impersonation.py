import json
import uuid
from core.models import User
from core.test_helpers import create_test_role, create_test_interactive_user
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
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
        self.superadmin_token_context = BaseTestContext(user=self.superadmin)
        self.superadmin_token = self.superadmin_token_context.get_jwt()
        # Create read-only role for users and roles
        read_role = create_test_role(perm_names=["gql_query_users_perms", "gql_query_roles_perms"], name="ReadOnlyUserRole")
        # Create regular user with read-only role
        self.regular_user = create_test_interactive_user(
            username="regular",
            password="password",
            roles=[read_role.id],
            custom_props={'email': "regular@test.com"}
        )
        self.regular_interactive = self.regular_user.i_user
        self.regular_token_context = BaseTestContext(user=self.regular_user)
        self.regular_token = self.regular_token_context.get_jwt()
        # Create user without rights
        self.no_rights_user = create_test_interactive_user(
            username="no_rights",
            password="password",
            roles=[],
            custom_props={'email': "no_rights@test.com"}
        )
        self.no_rights_interactive = self.no_rights_user.i_user
        # Invalid UUID
        self.invalid_uuid = "00000000-0000-0000-0000-000000000000"

    def test_impersonation_success(self):
        token = self.superadmin_token
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
                **self._instance_to_gql_input(
                    self.regular_interactive,
                    CreateUserMutation.Input,
                    {"language_id": "language", 'password': "_exclude_", "id": "_exclude_", "uuid": "i_user_id"}
                ),
                **self._instance_to_gql_input(
                    self.regular_user,
                    CreateUserMutation.Input,
                    {"id": "uuid", 'password': "_exclude_"}
                ),
                "lastName": "update",
                "clientMutationId": str(uuid.uuid4()),
                "userTypes": ["INTERACTIVE"]
            }
        }
        # First, without impersonation, superadmin can do it
        response = self.query(
            query,
            variables=variables,
            headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
        )
        result = self.get_mutation_result(
            variables['input']["clientMutationId"], token
        )
        self.assertEqual(result['data']['mutationLogs']['edges'][0]['node']['status'], 2)
        self.assertResponseNoErrors(response)
        variables['input']["lastName"] = "update1"
        variables['input']["clientMutationId"] = str(uuid.uuid4())
        # Now, impersonate no_rights_user, who doesn't have the right, so should fail
        response = self.query(
            query,
            variables=variables,
            headers={
                "HTTP_AUTHORIZATION": f"Bearer {token}",
                "HTTP_X_IMPERSONATE_USER": str(self.no_rights_user.id)
            }
        )

        result = self.get_mutation_result(
            variables['input']["clientMutationId"], token, allow_exceptions=False
        )
        # Should have errors, permission denied
        self.assertEqual(result['data']['mutationLogs']['edges'][0]['node']['status'], 1, result['data']['mutationLogs']['edges'][0]['node']['error'])

    def test_invalid_impersonation_uuid(self):
        token = self.superadmin_token

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
                **self._instance_to_gql_input(
                    self.regular_interactive,
                    CreateUserMutation.Input,
                    {"language_id": "language", 'password': "_exclude_"}
                ),
                **self._instance_to_gql_input(
                    self.regular_user,
                    CreateUserMutation.Input,
                    {'password': "_exclude_"}
                ),
                "lastName": "update2",
                "clientMutationId": str(uuid.uuid4()),
                "userTypes": ["INTERACTIVE"],
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
        # Should have auth error at GraphQL level (impersonation denied before reaching mutation resolver / log)
        self.assertResponseHasErrors(response)
        content = json.loads(response.content)
        self.assertTrue(
            "errors" in content
            or (content.get("data") and any(e and "NO_PERMISSION" in str(e) for e in (content.get("data") or {}).values()))
        )

    def test_non_superuser_impersonation(self):
        token = self.regular_token
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
                **self._instance_to_gql_input(
                    self.regular_interactive,
                    CreateUserMutation.Input,
                    {"language_id": "language", 'password': "_exclude_"}
                ),
                **self._instance_to_gql_input(
                    self.regular_user,
                    CreateUserMutation.Input,
                    {'password': "_exclude_"}
                ),
                "lastName": "update3",
                "clientMutationId": str(uuid.uuid4()),
                "userTypes": ["INTERACTIVE"]
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
        # Should have auth error at GraphQL level (non-super attempting impersonate denied before resolver)
        self.assertResponseHasErrors(response)
        content = json.loads(response.content)
        self.assertTrue(
            "errors" in content
            or (content.get("data") and any(e and "NO_PERMISSION" in str(e) for e in (content.get("data") or {}).values()))
        )

    def test_subsequent_calls_no_leakage(self):
        """Tests that after an impersonated call, a subsequent call without the header uses the original user (verifies ClearUserContextMiddleware + shared utility)."""
        token = self.superadmin_token
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
                **self._instance_to_gql_input(
                    self.regular_interactive,
                    CreateUserMutation.Input,
                    {"language_id": "language", 'password': "_exclude_", "id": "_exclude_", "uuid": "i_user_id"}
                ),
                **self._instance_to_gql_input(
                    self.regular_user,
                    CreateUserMutation.Input,
                    {"id": "uuid", 'password': "_exclude_"}
                ),
                "lastName": "update4",
                "clientMutationId": str(uuid.uuid4()),
                "userTypes": ["INTERACTIVE"]
            }
        }
        # First: impersonate no_rights_user -> should fail (status 1)
        self.query(
            query,
            variables=variables,
            headers={
                "HTTP_AUTHORIZATION": f"Bearer {token}",
                "HTTP_X_IMPERSONATE_USER": str(self.no_rights_user.uuid)
            }
        )
        # Note: the query response itself succeeds (returns internalId); the impersonation permission failure is recorded as status=1 in the mutation log (checked via get_mutation_result below in other tests)

        # Subsequent call WITHOUT impersonate header -> should succeed as superadmin (status 2, no leakage)
        variables["input"]["clientMutationId"] = str(uuid.uuid4())
        variables["input"]["lastName"] = "update5"
        response2 = self.query(
            query,
            variables=variables,
            headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
        )
        result2 = self.get_mutation_result(variables['input']["clientMutationId"], token)
        self.assertEqual(result2['data']['mutationLogs']['edges'][0]['node']['status'], 2)
        self.assertResponseNoErrors(response2)
