from django.test import TestCase
from unittest.mock import Mock, patch
from core.abs_calculation_rule import AbsStrategy
from core import datetime
from datetime import timedelta


class ConcreteCalculationRule(AbsStrategy):
    """Concrete implementation for testing abstract class"""
    version = 1
    uuid = "test-uuid-123"
    calculation_rule_name = "Test Calculation Rule"
    description = "Test description"
    impacted_class_parameter = [
        {
            "class": "TestClass",
            "parameters": [
                {"name": "param1", "type": "string"}
            ]
        }
    ]
    date_valid_from = datetime.datetime(2000, 1, 1)
    date_valid_to = None
    status = "active"
    from_to = [
        {"from": "ClassA", "to": "ClassB"},
        {"from": "ClassB", "to": "ClassC"}
    ]
    type = "test_type"
    sub_type = "test_sub_type"

    @classmethod
    def check_calculation(cls, instance):
        return True

    @classmethod
    def active_for_object(cls, instance, context, type=None, sub_type=None):
        return True

    @classmethod
    def calculate(cls, instance, *args, **kwargs):
        return {"result": "calculated"}

    @classmethod
    def convert(cls, instance, convert_to, **kwargs):
        return {"result": "converted"}


class AbsCalculationRulePropertyTest(TestCase):
    """Test property getters and setters"""

    def test_version_property(self):
        self.assertEqual(ConcreteCalculationRule.version, 1)
        ConcreteCalculationRule.version = 2
        self.assertEqual(ConcreteCalculationRule.version, 2)
        ConcreteCalculationRule.version = 1

    def test_uuid_property(self):
        self.assertEqual(ConcreteCalculationRule.uuid, "test-uuid-123")
        ConcreteCalculationRule.uuid = "new-uuid"
        self.assertEqual(ConcreteCalculationRule.uuid, "new-uuid")
        ConcreteCalculationRule.uuid = "test-uuid-123"

    def test_calculation_rule_name_property(self):
        self.assertEqual(ConcreteCalculationRule.calculation_rule_name, "Test Calculation Rule")
        ConcreteCalculationRule.calculation_rule_name = "New Name"
        self.assertEqual(ConcreteCalculationRule.calculation_rule_name, "New Name")
        ConcreteCalculationRule.calculation_rule_name = "Test Calculation Rule"

    def test_description_property(self):
        self.assertEqual(ConcreteCalculationRule.description, "Test description")
        ConcreteCalculationRule.description = "New description"
        self.assertEqual(ConcreteCalculationRule.description, "New description")
        ConcreteCalculationRule.description = "Test description"

    def test_impacted_class_parameter_property(self):
        expected = [{"class": "TestClass", "parameters": [{"name": "param1", "type": "string"}]}]
        self.assertEqual(ConcreteCalculationRule.impacted_class_parameter, expected)

    def test_type_property(self):
        self.assertEqual(ConcreteCalculationRule.type, "test_type")
        ConcreteCalculationRule.type = "new_type"
        self.assertEqual(ConcreteCalculationRule.type, "new_type")
        ConcreteCalculationRule.type = "test_type"

    def test_sub_type_property(self):
        self.assertEqual(ConcreteCalculationRule.sub_type, "test_sub_type")
        ConcreteCalculationRule.sub_type = "new_sub_type"
        self.assertEqual(ConcreteCalculationRule.sub_type, "new_sub_type")
        ConcreteCalculationRule.sub_type = "test_sub_type"

    def test_from_to_property(self):
        expected = [{"from": "ClassA", "to": "ClassB"}, {"from": "ClassB", "to": "ClassC"}]
        self.assertEqual(ConcreteCalculationRule.from_to, expected)

    def test_supports_advanced_criteria(self):
        # supports_advanced_criteria defaults to True: a real bool, read on the class.
        # It used to be a property object there (truthy), which graphql-core 3 refuses
        # to serialise as a Boolean.
        self.assertIs(ConcreteCalculationRule.supports_advanced_criteria, True)

        ConcreteCalculationRule.supports_advanced_criteria = False
        self.assertFalse(ConcreteCalculationRule.supports_advanced_criteria)

        ConcreteCalculationRule.supports_advanced_criteria = True
        self.assertTrue(ConcreteCalculationRule.supports_advanced_criteria)


class AbsCalculationRuleReadyTest(TestCase):
    """Test the ready() method that checks date validity"""

    def test_ready_with_valid_dates_no_end_date(self):
        """Test that status remains active when dates are valid and no end date"""
        rule = ConcreteCalculationRule
        rule.date_valid_from = datetime.datetime(2000, 1, 1)
        rule.date_valid_to = None
        rule.status = "active"

        rule.ready()

        self.assertEqual(rule.status, "active")

    def test_ready_with_future_start_date(self):
        """Test that status becomes inactive when start date is in future"""
        rule = ConcreteCalculationRule
        rule.date_valid_from = datetime.datetime.now() + timedelta(days=10)
        rule.date_valid_to = None
        rule.status = "active"

        rule.ready()

        self.assertEqual(rule.status, "inactive")

    def test_ready_with_past_end_date(self):
        """Test that status becomes inactive when end date is in past"""
        rule = ConcreteCalculationRule
        rule.date_valid_from = datetime.datetime(2000, 1, 1)
        rule.date_valid_to = datetime.datetime.now() - timedelta(days=10)
        rule.status = "active"

        rule.ready()

        self.assertEqual(rule.status, "inactive")

    def test_ready_with_valid_date_range(self):
        """Test that status remains active when within valid date range"""
        rule = ConcreteCalculationRule
        rule.date_valid_from = datetime.datetime.now() - timedelta(days=10)
        rule.date_valid_to = datetime.datetime.now() + timedelta(days=10)
        rule.status = "active"

        rule.ready()

        self.assertEqual(rule.status, "active")


class AbsCalculationRuleGetLinkedClassTest(TestCase):
    """Test the get_linked_class() method"""

    @patch('django.contrib.contenttypes.models.ContentType.objects.filter')
    def test_get_linked_class_with_valid_class_name(self, mock_filter):
        """Test getting linked classes for a valid model class"""
        mock_model = Mock()
        mock_model._meta.fields = [
            Mock(
                get_internal_type=lambda: "ForeignKey",
                remote_field=Mock(model=Mock(__name__="LinkedClass1"))
            ),
            Mock(
                get_internal_type=lambda: "ForeignKey",
                remote_field=Mock(model=Mock(__name__="User"))
            ),
            Mock(
                get_internal_type=lambda: "ForeignKey",
                remote_field=Mock(model=Mock(__name__="LinkedClass2"))
            ),
            Mock(get_internal_type=lambda: "CharField")
        ]

        mock_content_type = Mock()
        mock_content_type.model_class.return_value = mock_model
        mock_filter.return_value.first.return_value = mock_content_type

        result = ConcreteCalculationRule.get_linked_class(None, "TestModel")

        self.assertIn("LinkedClass1", result)
        self.assertIn("LinkedClass2", result)
        self.assertNotIn("User", result)

    def test_get_linked_class_with_none_class_name(self):
        """Test that returns Calculation when class_name is None"""
        result = ConcreteCalculationRule.get_linked_class(None, None)
        self.assertEqual(result, ["Calculation"])

    @patch('django.contrib.contenttypes.models.ContentType.objects.filter')
    def test_get_linked_class_with_nonexistent_class(self, mock_filter):
        """Test with a class that doesn't exist"""
        mock_filter.return_value.first.return_value = None

        result = ConcreteCalculationRule.get_linked_class(None, "NonexistentClass")

        self.assertEqual(result, [])


class AbsCalculationRuleGetRuleNameTest(TestCase):
    """Test the get_rule_name() method"""

    def test_get_rule_name_with_matching_class(self):
        """Test getting rule name when class matches"""
        result = ConcreteCalculationRule.get_rule_name(None, "TestClass")
        self.assertEqual(result, ConcreteCalculationRule)

    def test_get_rule_name_with_non_matching_class(self):
        """Test getting rule name when class doesn't match"""
        result = ConcreteCalculationRule.get_rule_name(None, "NonMatchingClass")
        self.assertIsNone(result)


class AbsCalculationRuleGetRuleDetailsTest(TestCase):
    """Test the get_rule_details() method"""

    def test_get_rule_details_with_matching_class(self):
        """Test getting rule details when class matches"""
        result = ConcreteCalculationRule.get_rule_details(None, "TestClass")

        expected = {
            "class": "TestClass",
            "parameters": [{"name": "param1", "type": "string"}]
        }
        self.assertEqual(result, expected)

    def test_get_rule_details_with_non_matching_class(self):
        """Test getting rule details when class doesn't match"""
        result = ConcreteCalculationRule.get_rule_details(None, "NonMatchingClass")
        self.assertIsNone(result)


class AbsCalculationRuleGetParametersTest(TestCase):
    """Test the get_parameters() method"""

    def test_get_parameters_with_matching_class_and_valid_instance(self):
        """Test getting parameters when class matches and check_calculation passes"""
        mock_instance = Mock()

        with patch.object(ConcreteCalculationRule, 'check_calculation', return_value=True):
            result = ConcreteCalculationRule.get_parameters(None, "TestClass", mock_instance)

        expected = [{"name": "param1", "type": "string"}]
        self.assertEqual(result, expected)

    def test_get_parameters_with_matching_class_but_invalid_instance(self):
        """Test getting parameters when class matches but check_calculation fails"""
        mock_instance = Mock()

        with patch.object(ConcreteCalculationRule, 'check_calculation', return_value=False):
            result = ConcreteCalculationRule.get_parameters(None, "TestClass", mock_instance)

        self.assertIsNone(result)

    def test_get_parameters_with_non_matching_class(self):
        """Test getting parameters when class doesn't match"""
        mock_instance = Mock()

        result = ConcreteCalculationRule.get_parameters(None, "NonMatchingClass", mock_instance)
        self.assertIsNone(result)


class AbsCalculationRuleGetConvertFromToTest(TestCase):
    """Test the get_convert_from_to() method"""

    def test_get_convert_from_to(self):
        """Test getting conversion possibilities"""
        result = ConcreteCalculationRule.get_convert_from_to()

        expected = [
            {
                "calc_uuid": "test-uuid-123",
                "from": "ClassA",
                "to": "ClassB"
            },
            {
                "calc_uuid": "test-uuid-123",
                "from": "ClassB",
                "to": "ClassC"
            }
        ]

        self.assertEqual(result, expected)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["from"], "ClassA")
        self.assertEqual(result[0]["to"], "ClassB")
        self.assertEqual(result[1]["from"], "ClassB")
        self.assertEqual(result[1]["to"], "ClassC")


class AbsCalculationRuleRunConvertTest(TestCase):
    """Test the run_convert() method"""

    def test_run_convert_with_matching_conversion(self):
        """Test running conversion with matching from/to"""
        mock_instance = Mock()
        mock_instance.__class__.__name__ = "ClassA"

        with patch.object(ConcreteCalculationRule, 'convert', return_value={"converted": True}) as mock_convert:
            result = ConcreteCalculationRule.run_convert(mock_instance, "ClassB")

        mock_convert.assert_called_once()
        self.assertEqual(result, {"converted": True})

    def test_run_convert_with_non_matching_conversion(self):
        """Test running conversion with non-matching from/to"""
        mock_instance = Mock()
        mock_instance.__class__.__name__ = "ClassX"

        result = ConcreteCalculationRule.run_convert(mock_instance, "ClassY")
        self.assertIsNone(result)

    def test_run_convert_with_contract_special_case(self):
        """Test that Contract is converted to ContractContributionPlanDetails"""
        mock_instance = Mock()
        mock_instance.__class__.__name__ = "Contract"

        class ContractConversionRule(ConcreteCalculationRule):
            from_to = [{"from": "ContractContributionPlanDetails", "to": "Payment"}]

        with patch.object(ContractConversionRule, 'convert', return_value={"converted": True}) as mock_convert:
            result = ContractConversionRule.run_convert(mock_instance, "Payment")

        mock_convert.assert_called_once()
        self.assertEqual(result, {"converted": True})


class AbsCalculationRuleRunCalculationRulesTest(TestCase):
    """Test the run_calculation_rules() method"""

    @patch.object(ConcreteCalculationRule, 'get_linked_class')
    @patch.object(ConcreteCalculationRule, 'calculate_if_active_for_object')
    def test_run_calculation_rules_with_linked_class(self, mock_calc_if_active, mock_get_linked):
        """Test running calculation rules with linked classes"""
        mock_instance = Mock()
        mock_instance.__class__.__name__ = "TestInstance"
        mock_user = Mock()

        mock_get_linked.return_value = ["TestClass"]
        mock_calc_if_active.return_value = {"result": "success"}

        result = ConcreteCalculationRule.run_calculation_rules(
            None, mock_instance, mock_user, "test_context"
        )

        self.assertEqual(result, {"result": "success"})
        mock_calc_if_active.assert_called_once()

    @patch.object(ConcreteCalculationRule, 'get_linked_class')
    def test_run_calculation_rules_with_calculation_attribute(self, mock_get_linked):
        """Test that instance class is added when it has calculation attribute"""
        mock_instance = Mock()
        mock_instance.__class__.__name__ = "PaymentPlan"
        mock_instance.calculation = "some-calc-id"
        mock_user = Mock()

        mock_get_linked.return_value = ["OtherClass"]

        with patch.object(ConcreteCalculationRule, 'calculate_if_active_for_object'):
            ConcreteCalculationRule.run_calculation_rules(
                None, mock_instance, mock_user, "test_context"
            )

        args = mock_get_linked.call_args[0]
        self.assertEqual(args[1], "PaymentPlan")
