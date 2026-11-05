from django.test import SimpleTestCase

from core.apps import CoreConfig
from core.utils import build_permissions_map, permissions_map_key


class PermissionsMapTestCase(SimpleTestCase):
    def test_key_of_gql_rights(self):
        self.assertEqual(permissions_map_key("core", "gql_query_users_perms"), "core.users")
        self.assertEqual(
            permissions_map_key("core", "gql_mutation_create_roles_perms"), "core.create_roles"
        )

    def test_key_of_other_rights(self):
        self.assertEqual(permissions_map_key("claim", "claim_print_perms"), "claim.claim_print")

    def test_map_is_built_from_the_loaded_modules(self):
        """The map is generated, not read from a committed file: core's rights are in it."""
        mapping = build_permissions_map()
        self.assertEqual(list(mapping), sorted(mapping))
        self.assertEqual(
            str(mapping["core.users"]), str(CoreConfig.gql_query_users_perms[-1])
        )
