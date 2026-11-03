"""Officer and claim-administrator location scoping (OP-3197).

Both properties used to resolve the hierarchy in Python - a `parent` walk per
village for the officer, a level-at-a-time descent for the claim admin - and
hand the answer back as a literal uuid list. These pin the set they return and
the fact that it now costs one query.
"""

from django.test import TestCase

from core.test_helpers import create_test_claim_admin, create_test_officer
from location.test_helpers import (
    create_test_health_facility,
    create_test_location,
    create_test_village,
)


class OfficerAllowedLocationsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # one full R > D > W > V chain, plus a second village under the same
        # ward so the deduplication at each level has something to collapse
        cls.village_a = create_test_village({"code": "OP3197A"})
        cls.ward = cls.village_a.parent
        cls.district = cls.ward.parent
        cls.region = cls.district.parent
        cls.village_b = create_test_location(
            "V", custom_props={"code": "OP3197B", "parent": cls.ward}
        )
        # an unrelated hierarchy that must never appear
        cls.other_village = create_test_village({"code": "OP3197Z"})

    def test_returns_the_villages_and_their_ancestors(self):
        officer = create_test_officer(
            custom_props={"code": "OP3197EO"},
            villages=[self.village_a, self.village_b],
        )

        self.assertEqual(
            set(officer.officer_allowed_locations.values_list("id", flat=True)),
            {
                self.village_a.id,
                self.village_b.id,
                self.ward.id,
                self.district.id,
                self.region.id,
            },
        )

    def test_leaves_an_unrelated_branch_out(self):
        officer = create_test_officer(
            custom_props={"code": "OP3197EO2"}, villages=[self.village_a]
        )
        allowed = set(officer.officer_allowed_locations.values_list("id", flat=True))

        self.assertNotIn(self.other_village.id, allowed)
        self.assertNotIn(self.other_village.parent_id, allowed)
        self.assertNotIn(self.village_b.id, allowed)

    def test_the_query_count_does_not_grow_with_the_number_of_villages(self):
        """The point of the change: constant cost, not 1 + N * (1 + depth).

        The absolute number is not asserted - the cached managers add their own
        fixed overhead depending on whether a lookup is warm - but it must not
        move when villages are added.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        one = create_test_officer(
            custom_props={"code": "OP3197N1"}, villages=[self.village_a]
        )
        many = create_test_officer(
            custom_props={"code": "OP3197N2"},
            villages=[self.village_a, self.village_b]
            + [
                create_test_location(
                    "V", custom_props={"code": f"OP3197N{i}", "parent": self.ward}
                )
                for i in range(5)
            ],
        )

        def cost(officer):
            list(officer.officer_allowed_locations)  # warm anything cacheable
            with CaptureQueriesContext(connection) as ctx:
                list(officer.officer_allowed_locations)
            return len(ctx.captured_queries)

        self.assertEqual(cost(one), cost(many))

    def test_an_officer_with_no_village_sees_nothing(self):
        officer = create_test_officer(custom_props={"code": "OP3197EO4"}, villages=[])

        self.assertEqual(list(officer.officer_allowed_locations), [])


class ClaimAdminAllowedLocationsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.village = create_test_village({"code": "OP3197CA"})
        cls.ward = cls.village.parent
        cls.district = cls.ward.parent
        cls.region = cls.district.parent
        cls.other_village = create_test_village({"code": "OP3197CAZ"})

    def _claim_admin(self, code):
        hf = create_test_health_facility(
            code=code, location_id=self.district.id
        )
        return create_test_claim_admin(
            custom_props={"code": code, "health_facility": hf}
        )

    def test_returns_the_district_its_parent_and_everything_below(self):
        admin = self._claim_admin("OP3197H1")

        self.assertEqual(
            set(admin.officer_allowed_locations.values_list("id", flat=True)),
            {self.region.id, self.district.id, self.ward.id, self.village.id},
        )

    def test_leaves_an_unrelated_branch_out(self):
        admin = self._claim_admin("OP3197H2")
        allowed = set(admin.officer_allowed_locations.values_list("id", flat=True))

        self.assertNotIn(self.other_village.id, allowed)
        self.assertNotIn(self.other_village.parent_id, allowed)
