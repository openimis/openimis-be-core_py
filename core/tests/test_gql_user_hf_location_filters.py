"""GQL createUser with HF attaches ClaimAdmin, whose location filter overrides EO villages."""

import json

from django.core.cache import cache

from core.rights_role_test_case import RightsRoleGraphQLTestCase
from core.test_helpers import (
    create_claim_admin_role,
    create_data_entry_clerk_hf_role,
    create_test_interactive_user,
)
from core.user_types import UT_CLAIM_ADMIN, UT_INTERACTIVE, UT_OFFICER
from location.models import Location, LocationManager, OfficerVillage, UserDistrict
from location.test_helpers import (
    create_basic_test_locations,
    create_test_health_facility,
    create_test_village,
)


class GqlUserHfLocationFilterTests(RightsRoleGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_basic_test_locations()
        cls.admin = create_test_interactive_user(username="gqlhfadm")
        cls.eo_village = create_test_village()
        cls.eo_district = cls.eo_village.parent.parent
        cls.hf_district = Location.objects.get(code="R2D1", validity_to__isnull=True)
        cls.hf = create_test_health_facility(
            code="GQLHFA", location_id=cls.hf_district.id
        )
        cls.ca_role = create_claim_admin_role()
        cls.custom_role = create_data_entry_clerk_hf_role()

    def _create_mixed_user(self, username):
        cache.clear()
        return self.create_gql_user_with_hf(
            self.admin,
            username=username,
            health_facility=self.hf,
            roles=[self.ca_role, self.custom_role],
            districts=[self.eo_district],
            villages=[self.eo_village],
            include_officer=True,
            include_claim_admin=True,
        )

    def test_gql_hf_user_gets_ca_and_eo_and_std_ca_role(self):
        user = self._create_mixed_user("ghfca1")
        self.assertIsNotNone(user.i_user)
        self.assertIsNotNone(user.claim_admin)
        self.assertIsNotNone(user.officer)
        self.assertEqual(user.claim_admin.health_facility_id, self.hf.id)
        self.assertEqual(user.i_user.health_facility_id, self.hf.id)
        self.assertTrue(user.i_user.is_claim_admin)
        self.assertTrue(user.i_user.is_officer)
        role_ids = set(
            user.i_user.user_roles.filter(validity_to__isnull=True).values_list(
                "role_id", flat=True
            )
        )
        self.assertIn(self.ca_role.id, role_ids)
        self.assertIn(self.custom_role.id, role_ids)
        self.assertTrue(
            OfficerVillage.objects.filter(
                officer=user.officer,
                location=self.eo_village,
                validity_to__isnull=True,
            ).exists()
        )
        self.assertTrue(
            UserDistrict.objects.filter(
                user=user.i_user,
                location=self.eo_district,
                validity_to__isnull=True,
            ).exists()
        )

    def test_gql_hf_user_location_filter_follows_hf_not_eo_villages(self):
        user = self._create_mixed_user("ghfca2")
        cache.clear()
        allowed = LocationManager().get_allowed_ids(user._u)
        self.assertEqual(allowed, [self.hf_district.id])
        self.assertNotIn(self.eo_village.id, allowed)
        self.assertNotIn(self.eo_district.id, allowed)
        self.assertTrue(
            LocationManager().is_allowed(user, [self.hf_district.id], strict=False)
        )
        self.assertFalse(
            LocationManager().is_allowed(user, [self.eo_village.id], strict=True)
        )

    def test_gql_officer_without_ca_uses_village_filter(self):
        user = self.create_gql_user_with_hf(
            self.admin,
            username="ghfeo1",
            health_facility=self.hf,
            roles=[self.custom_role],
            districts=[self.eo_district],
            villages=[self.eo_village],
            include_officer=True,
            include_claim_admin=False,
        )
        cache.clear()
        self.assertIsNone(user.claim_admin)
        self.assertIsNotNone(user.officer)
        allowed = LocationManager().get_allowed_ids(user._u)
        self.assertIn(self.eo_village.id, allowed)
        self.assertNotIn(self.hf_district.id, allowed)

    def test_gql_user_query_returns_mixed_types(self):
        user = self._create_mixed_user("ghfca3")
        response = self.assert_gql_ok(
            self.admin,
            """
            query ($username: String!) {
              users(username: $username, first: 1) {
                edges { node { username userTypes } }
              }
            }
            """,
            variables={"username": user.username},
        )
        node = json.loads(response.content)["data"]["users"]["edges"][0]["node"]
        self.assertCountEqual(
            node["userTypes"], [UT_INTERACTIVE, UT_CLAIM_ADMIN, UT_OFFICER]
        )
