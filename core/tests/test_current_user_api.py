from types import SimpleNamespace
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import User
from core.serializers import ClaimAdminSerializer, OfficerSerializer
from core.test_helpers import (
    create_test_claim_admin,
    create_test_interactive_user,
)
from core.views import UserViewSet


class CurrentUserApiTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = create_test_interactive_user(
            username="current_user_api_test",
            custom_props={
                "email": "current_user@test.org",
                "phone": "+23700000000",
            },
        )

    def test_current_user_non_regression_and_i_user_enrichment(self):
        request = self.factory.get("/core/users/current_user/")
        force_authenticate(request, user=self.user)

        response = UserViewSet.as_view({"get": "current_user"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("id", response.data)
        self.assertIn("username", response.data)
        self.assertIn("i_user", response.data)
        self.assertIn("t_user", response.data)

        self.assertIn("rights", response.data["i_user"])
        self.assertIn("email", response.data["i_user"])
        self.assertIn("phone", response.data["i_user"])

    def test_current_user_null_officer_and_claim_admin(self):
        request = self.factory.get("/core/users/current_user/")
        force_authenticate(request, user=self.user)

        response = UserViewSet.as_view({"get": "current_user"})(request)

        self.assertEqual(response.status_code, 200)

        self.assertIn("officer", response.data)
        self.assertIn("claim_admin", response.data)

        self.assertIsNone(response.data["officer"])
        self.assertIsNone(response.data["claim_admin"])

    def test_current_user_claim_admin_payload(self):
        claim_admin = create_test_claim_admin(
            custom_props={"code": "CURRENT_USER_CA"}
        )
        user = User.objects.create(
            username="current_user_ca_test",
            i_user=self.user.i_user,
            claim_admin=claim_admin,
        )

        request = self.factory.get("/core/users/current_user/")
        force_authenticate(request, user=user)

        response = UserViewSet.as_view({"get": "current_user"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data["claim_admin"])
        self.assertEqual(
            response.data["claim_admin"]["healthFacility"]["code"],
            claim_admin.health_facility.code,
        )
        self.assertIsNone(response.data["officer"])

    def test_officer_serializer_structure(self):
        parent_location = SimpleNamespace(
            id=2,
            uuid=uuid4(),
            code="EST",
            name="Est",
            type="R",
            parent=None,
        )

        location = SimpleNamespace(
            id=3,
            uuid=uuid4(),
            code="BER",
            name="Bertoua",
            type="D",
            parent=parent_location,
        )

        officer = SimpleNamespace(
            id=11,
            uuid=uuid4(),
            code="OFF001",
            dob=None,
            address="Address",
            last_name="Sandjong",
            other_names="Paul",
            location=location,
        )

        data = OfficerSerializer(officer).data

        self.assertEqual(data["id"], 11)
        self.assertEqual(data["lastName"], "Sandjong")
        self.assertEqual(data["otherNames"], "Paul")
        self.assertEqual(data["location"]["parent"]["code"], "EST")

    def test_claim_admin_serializer_structure(self):
        parent_location = SimpleNamespace(
            id=2,
            uuid=uuid4(),
            code="EST",
            name="Est",
            type="R",
            parent=None,
        )

        location = SimpleNamespace(
            id=3,
            uuid=uuid4(),
            code="BER",
            name="Bertoua",
            type="D",
            parent=parent_location,
        )

        services_pricelist = SimpleNamespace(
            id=10,
            uuid=str(uuid4()),
        )

        health_facility = SimpleNamespace(
            id=56,
            uuid=uuid4(),
            code="ES001",
            name="HR Bertoua",
            level="H",
            services_pricelist=services_pricelist,
            items_pricelist=None,
            contract_start_date=None,
            contract_end_date=None,
            location=location,
        )

        claim_admin = SimpleNamespace(
            id=22,
            uuid=uuid4(),
            code="paul",
            email_id="paul@gmail.com",
            phone="",
            dob=None,
            last_name="Sandjong",
            other_names="Paul",
            health_facility=health_facility,
        )

        data = ClaimAdminSerializer(claim_admin).data

        self.assertEqual(data["id"], 22)
        self.assertEqual(data["emailId"], "paul@gmail.com")
        self.assertEqual(data["healthFacility"]["code"], "ES001")
        self.assertEqual(
            data["healthFacility"]["location"]["parent"]["code"],
            "EST",
        )
