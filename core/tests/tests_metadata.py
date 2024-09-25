from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from core.test_helpers import create_test_interactive_user
import uuid

class CurrentUserAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('user-current-user')  # This matches the DRF default naming for actions
        
        # Create a test user
        self.user = create_test_interactive_user()
        

    def test_get_current_user(self):
        # Authenticate the user
        self.client.force_authenticate(user=self.user)
        
        # Make the GET request
        response = self.client.get(self.url)
        
        # Check status code
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check the structure of the response
        data = response.json()
        
        # Check main user fields
        self.assertIn('id', data)
        self.assertIsInstance(data['id'], str)
        self.assertIn('username', data)
        self.assertIsInstance(data['username'], str)
        
        # Check i_user fields
        self.assertIn('i_user', data)
        i_user = data['i_user']
        self.assertIsInstance(i_user, dict)
        
        expected_i_user_fields = [
            'id', 'language', 'last_name', 'other_names', 
            'health_facility_id', 'rights', 'has_password'
        ]
        for field in expected_i_user_fields:
            self.assertIn(field, i_user)
        
        # Check specific field types
        self.assertIsInstance(i_user['id'], int)
        self.assertIsInstance(i_user['language'], str)
        self.assertIsInstance(i_user['last_name'], str)
        self.assertIsInstance(i_user['other_names'], str)
        self.assertIsInstance(i_user['rights'], list)
        self.assertIsInstance(i_user['has_password'], bool)
        
        # Check t_user field
        self.assertIn('t_user', data)
        self.assertIsNone(data['t_user'])  # Assuming t_user is always null in this case

    def test_unauthenticated_access(self):
        # Test without authentication
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
