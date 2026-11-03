"""Claim administrators are only visible within the user's districts (audit C3)."""

import json

from django.core.cache import cache
from django.test import override_settings

from core.models import ClaimAdmin
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.test_helpers import create_right_only_user, create_test_claim_admin
from location.models import Location
from location.test_helpers import create_basic_test_locations, create_test_health_facility

CLAIM_ADMINS_QUERY = """
query {
  claimAdmins(first: 50) { edges { node { code } } }
}
"""


@override_settings(ROW_SECURITY=True)
class ClaimAdminRowSecurityTests(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_basic_test_locations()
        district_a = Location.objects.get(code="R1D1", validity_to__isnull=True)
        district_b = Location.objects.get(code="R2D1", validity_to__isnull=True)
        hf_a = create_test_health_facility(code="CAHFA", location_id=district_a.id)
        hf_b = create_test_health_facility(code="CAHFB", location_id=district_b.id)
        create_test_claim_admin(custom_props={"code": "CARS-A", "health_facility": hf_a})
        create_test_claim_admin(custom_props={"code": "CARS-B", "health_facility": hf_b})

        perm = ["gql_query_claim_administrator_perms"]
        cls.user_a = create_right_only_user("carsusera", perm, district_codes=["R1D1"])
        # R2D2 holds no health facility: the resolver used to drop its filter then.
        cls.user_no_hf = create_right_only_user("carsnohf", perm, district_codes=["R2D2"])
        cache.clear()

    def _codes(self, user):
        token = BaseTestContext(user=user).get_jwt()
        response = self.query(CLAIM_ADMINS_QUERY, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"})
        self.assertResponseNoErrors(response)
        edges = json.loads(response.content)["data"]["claimAdmins"]["edges"]
        return {e["node"]["code"] for e in edges} & {"CARS-A", "CARS-B"}

    def test_model_scope_keeps_own_district(self):
        codes = set(
            ClaimAdmin.get_queryset(None, self.user_a).filter(code__startswith="CARS-")
            .values_list("code", flat=True)
        )
        self.assertEqual(codes, {"CARS-A"})

    def test_graphql_keeps_own_district(self):
        self.assertEqual(self._codes(self.user_a), {"CARS-A"})

    def test_district_without_health_facility_sees_none(self):
        self.assertEqual(self._codes(self.user_no_hf), set())
