"""coerce_mutation_data, run by the worker on async mutations, accepts null enums."""
import graphene
from django.test import SimpleTestCase

from core.schema import OpenIMISMutation


class CeilingType(graphene.Enum):
    INSUREE = "I"
    TREATMENT = "T"


class CoerceInput(OpenIMISMutation.Input):
    ceiling_type = graphene.Field(CeilingType)
    required_ceiling_type = graphene.Field(graphene.NonNull(CeilingType))


class CoerceMutationDataTest(SimpleTestCase):
    def test_optional_enum_null_is_kept(self):
        # A product with no ceiling type sends `ceilingType: null` back on update;
        # hasattr(enum, None) raised "attribute name must be string" (OP-3283).
        coerced = OpenIMISMutation.coerce_mutation_data(
            {"ceiling_type": None}, input_class=CoerceInput
        )
        self.assertEqual(coerced, {"ceiling_type": None})

    def test_non_null_enum_null_is_kept(self):
        coerced = OpenIMISMutation.coerce_mutation_data(
            {"required_ceiling_type": None}, input_class=CoerceInput
        )
        self.assertEqual(coerced, {"required_ceiling_type": None})

    def test_enum_name_is_coerced_to_value(self):
        coerced = OpenIMISMutation.coerce_mutation_data(
            {"ceiling_type": "TREATMENT", "required_ceiling_type": "INSUREE"},
            input_class=CoerceInput,
        )
        self.assertEqual(coerced, {"ceiling_type": "T", "required_ceiling_type": "I"})
