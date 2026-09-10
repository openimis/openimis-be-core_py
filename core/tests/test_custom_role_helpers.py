from django.test import TestCase

from core.test_helpers import (
    create_claim_admin_role,
    create_data_entry_clerk_hf_role,
    create_hf_bound_role_user,
    create_right_only_user,
    resolve_perm_right_ids,
)
from location.test_helpers import (
    create_basic_test_locations,
    create_test_health_facility,
    create_test_village,
)


class CustomRoleHelperTests(TestCase):
    def test_right_only_user_has_exactly_named_perms(self):
        user = create_right_only_user("helper_ro", ["gql_query_users_perms"])
        rights = resolve_perm_right_ids(["gql_query_users_perms"])
        self.assertTrue(user.has_perms(rights))
        other = resolve_perm_right_ids(["gql_mutation_create_users_perms"])
        self.assertFalse(user.has_perms(other))

    def test_hf_bound_user_has_std_claim_admin_and_custom_role(self):
        create_basic_test_locations()
        village = create_test_village()
        hf = create_test_health_facility(code="HLPTHF", location_id=village.parent.parent.id)
        extra = create_data_entry_clerk_hf_role()
        user = create_hf_bound_role_user(
            "helper_hf",
            extra,
            health_facility=hf,
            with_officer=True,
            villages=[village],
        )
        self.assertIsNotNone(user.claim_admin)
        self.assertEqual(user.claim_admin.health_facility_id, hf.id)
        self.assertIsNotNone(user.officer)
        role_ids = set(
            user.i_user.user_roles.filter(validity_to__isnull=True).values_list(
                "role_id", flat=True
            )
        )
        self.assertIn(create_claim_admin_role().id, role_ids)
        self.assertIn(extra.id, role_ids)
        self.assertTrue(
            user.has_perms(resolve_perm_right_ids(["gql_mutation_create_claims_perms"]))
        )
