import unittest
from unittest.mock import patch

from core.test_helpers import create_test_role


class CreateTestRoleMockTest(unittest.TestCase):
    @patch('core.test_helpers.role_right_ids')
    @patch('core.test_helpers.RoleRightFactory')
    @patch('core.test_helpers.RoleFactory')
    @patch('core.test_helpers.Role')
    def test_create_test_role_success(self, MockRole, MockRoleFactory, MockRoleRightFactory, mock_role_right_ids):
        # Setup mocks
        MockRole.objects.filter.return_value.first.return_value = None
        mock_role_right_ids.return_value = [1]

        # Call function
        role = create_test_role(perm_names=['perm1'], name="TestRole")

        # Assertions
        self.assertEqual(role, MockRoleFactory.return_value)
        MockRoleFactory.assert_called_once()
        MockRoleRightFactory.assert_called_once()

    @patch('core.test_factories.collect_all_gql_permissions')
    @patch('core.test_helpers.Role')
    def test_create_test_role_failure(self, MockRole, mock_collect_perms):
        # Setup mocks
        mock_collect_perms.return_value = {
            'app1': {'perm1': [1]}
        }
        MockRole.objects.filter.return_value.first.return_value = None

        # Call function and expect exception. The factories are deliberately left unpatched:
        # reaching them would hit the database, so this also pins validation before any write.
        with self.assertRaises(Exception) as cm:
            create_test_role(perm_names=['invalid_perm'], name="TestRole")

        self.assertEqual(str(cm.exception), "Permission invalid_perm not found")


if __name__ == '__main__':
    unittest.main()
