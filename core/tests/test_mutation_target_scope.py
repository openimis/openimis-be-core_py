"""Shared update/delete paths look their target up through row security (audit H21, S3)."""

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, override_settings

from core.gql.gql_mutations import ObjectNotExistException
from core.gql.gql_mutations.base_mutation import BaseUpdateMutationMixin
from core.models import ClaimAdmin, target_queryset
from core.services import BaseService
from core.test_helpers import create_right_only_user, create_test_claim_admin
from location.models import Location
from location.test_helpers import create_basic_test_locations, create_test_health_facility


class _UpdateClaimAdmin(BaseUpdateMutationMixin):
    _model = ClaimAdmin


class _ClaimAdminService(BaseService):
    OBJECT_TYPE = ClaimAdmin


@override_settings(ROW_SECURITY=True)
class MutationTargetScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_basic_test_locations()
        district_a = Location.objects.get(code="R1D1", validity_to__isnull=True)
        district_b = Location.objects.get(code="R2D1", validity_to__isnull=True)
        hf_a = create_test_health_facility(code="H21HFA", location_id=district_a.id)
        hf_b = create_test_health_facility(code="H21HFB", location_id=district_b.id)
        cls.admin_a = create_test_claim_admin(custom_props={"code": "H21-A", "health_facility": hf_a})
        cls.admin_b = create_test_claim_admin(custom_props={"code": "H21-B", "health_facility": hf_b})
        cls.user_a = create_right_only_user("h21usera", [], district_codes=["R1D1"])

    def setUp(self):
        cache.clear()

    def test_target_queryset_is_the_readable_rows(self):
        codes = set(
            target_queryset(ClaimAdmin, self.user_a)
            .filter(code__startswith="H21-")
            .values_list("code", flat=True)
        )
        self.assertEqual(codes, {"H21-A"})

    def test_mutation_mixin_refuses_foreign_target(self):
        # Validation only checks existence, so a subclass's permission check
        # answers first; the write itself looks the target up scoped.
        _UpdateClaimAdmin._validate_mutation(self.user_a, uuid=self.admin_b.uuid)
        with self.assertRaises(ObjectNotExistException):
            _UpdateClaimAdmin._mutate(self.user_a, uuid=self.admin_b.uuid, name="H21")

    def test_service_refuses_foreign_target(self):
        service = _ClaimAdminService(self.user_a)
        self.assertEqual(service._get_target(self.admin_a.id), self.admin_a)
        with self.assertRaises(ObjectDoesNotExist):
            service._get_target(self.admin_b.id)
