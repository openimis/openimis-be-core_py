"""GQL createUser as Enrolment Officer: village filter, not UserDistrict or HF."""

import json

from django.core.cache import cache

from core.rights_role_test_case import RightsRoleGraphQLTestCase
from core.test_helpers import (
    create_enrolment_officer_role,
    create_test_interactive_user,
)
from core.user_types import UT_INTERACTIVE, UT_OFFICER
from location.models import LocationManager, OfficerVillage, UserDistrict
from location.test_helpers import (
    create_basic_test_locations,
    create_test_village,
)


class GqlUserEoLocationFilterTests(RightsRoleGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_basic_test_locations()
        cls.admin = create_test_interactive_user(username="gqleoadm")
        cls.eo_village = create_test_village(custom_props={"code": "EOVIL1"})
        cls.other_village = create_test_village(custom_props={"code": "EOVIL2"})
        cls.eo_district = cls.eo_village.parent.parent
        cls.other_district = cls.other_village.parent.parent
        cls.eo_role = create_enrolment_officer_role()

    def _create_eo_user(self, username):
        cache.clear()
        return self.create_gql_user_with_hf(
            self.admin,
            username=username,
            health_facility=None,
            roles=[self.eo_role],
            districts=[self.other_district],
            villages=[self.eo_village],
            include_officer=True,
            include_claim_admin=False,
        )

    def test_gql_eo_user_gets_officer_and_villages_not_ca(self):
        user = self._create_eo_user("geo1")
        self.assertIsNotNone(user.i_user)
        self.assertIsNotNone(user.officer)
        self.assertIsNone(user.claim_admin)
        self.assertTrue(user.i_user.is_officer)
        self.assertFalse(user.i_user.is_claim_admin)
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
                location=self.other_district,
                validity_to__isnull=True,
            ).exists()
        )

    def test_gql_eo_user_location_filter_follows_villages_not_districts(self):
        user = self._create_eo_user("geo2")
        cache.clear()
        allowed = LocationManager().get_allowed_ids(user._u)
        self.assertIn(self.eo_village.id, allowed)
        self.assertNotIn(self.other_village.id, allowed)
        self.assertNotIn(self.other_district.id, allowed)
        self.assertTrue(
            LocationManager().is_allowed(user, [self.eo_village.id], strict=False)
        )
        self.assertFalse(
            LocationManager().is_allowed(user, [self.other_village.id], strict=True)
        )

    def test_gql_user_query_returns_officer_type(self):
        user = self._create_eo_user("geo3")
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
        self.assertCountEqual(node["userTypes"], [UT_INTERACTIVE, UT_OFFICER])
