from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from core.test_helpers import create_test_interactive_user
from core.models.user import User

from dataclasses import dataclass
from graphql_jwt.shortcuts import get_token


@dataclass
class DummyContext:
    """ Just because we need a context to generate. """
    user: User


class CurrentUserAPITest(APITestCase):
    admin_token = None
    admin_user = None
    admin_password = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = APIClient()
        cls.admin_password = "testCUAdmin?1"
        cls.admin_user = create_test_interactive_user(username="testCUAdmin", password=cls.admin_password)
        cls.admin_token = get_token(cls.admin_user, DummyContext(user=cls.admin_user))

    def test_authenticated_get_current_user(self):
        url = '/api/core/users/current_user/'
        # Authenticate the client using JWT token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Assert response contains user data, e.g., username or id
        self.assertEqual(response.data['username'], self.admin_user.username)
        self.assertIn("default_rows_per_page", response.data["i_user"])

    def test_unauthenticated_get_current_user(self):
        url = '/api/core/users/current_user/'
        # No authentication
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)  # Or 403, depending on permissions
