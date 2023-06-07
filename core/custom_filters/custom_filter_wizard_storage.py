import logging
import re

from collections import namedtuple
from typing import List

from core.custom_filters.custom_filter_registry_point import CustomFilterRegistryPoint
from core.custom_filters import CustomFilterWizardInterface


logger = logging.getLogger(__name__)


class CustomFilterWizardStorage:
    """
        Class responsible for storing information on how to create filters based on the context of
        a particular wizard creator. This hub provides information about the method for building
        filters for a chosen field in specific object.

        Constants:
            __KEY_FOR_OBTAINING_CLASS: Indicates which element from the registry points should be
                                       considered to retrieve information about the registered CustomFilterWizard class.
            __FIELD: Identifies the first value of the final output tuple for building filters.
            __FILTER: Identifies the second value of the final output tuple for building filters.
            __VALUE: Identifies the third value of the final output tuple for building filters.
    """

    __KEY_FOR_OBTAINING_CLASS = 'class_reference'
    __FIELD = 'field'
    __FILTER = 'filter'
    __TYPE = 'type'

    @classmethod
    def build_custom_filters_definition(cls, module_name: str, object_type: str, **kwargs) -> List[namedtuple]:
        """
        Build the final outcome for creating a filter based on the information provided by
        a registered custom filter wizard for the specified module name and object type.

        The output is a list of named tuples (from the collections package). Each named tuple is built
        in the following format: <Type>(field=<str>, filter=<str>, type=<str>)

        Example named tuple: BenefitPlan(field='income', filter='lt, gte, icontains, exact', value='')

        :param module_name: The name of the module installed in openIMIS, required to retrieve information
                            about the possible ways of building filters for that specific module.
        :type module_name: str
        :param object_type: The name of the object type for which the filter building information is needed.
        :type object_type: str

        :return: A list of named tuples representing the final outcome for creating a filter.
        :rtype: List[namedtuple]
        """
        output_of_possible_filters = []
        registered_filter_wizards = CustomFilterRegistryPoint.REGISTERED_CUSTOM_FILTER_WIZARDS
        if module_name in registered_filter_wizards:
            for registered_filter_wizard in registered_filter_wizards[module_name]:
                if cls.__KEY_FOR_OBTAINING_CLASS not in registered_filter_wizard:
                    continue
                wizard_filter_class = cls.__create_instance_of_wizard_class(registered_filter_wizard)
                if not cls.__check_object_type(wizard_filter_class, object_type):
                    continue
                output_of_possible_filters.extend(
                    cls.__run_load_definition_object_in_wizard(wizard_filter_class, **kwargs)
                )
        return output_of_possible_filters

    @classmethod
    def apply_filter_to_queryset(cls, custom_filters, query):
        for filter_part in custom_filters:
            field, value = filter_part.split('=')
            field, value_type = field.rsplit('__', 1)
            value = cls.__cast_value(value, value_type)
            filter_kwargs = {f"json_ext__{field}": value}
            query = query.filter(**filter_kwargs)
        return query

    @classmethod
    def __run_load_definition_object_in_wizard(
        cls,
        wizard_filter_class: CustomFilterWizardInterface,
        **kwargs
    ) -> List[namedtuple]:
        wizard_filter_tuple_type = namedtuple(
            wizard_filter_class.get_type_of_object(),
            [cls.__FIELD, cls.__FILTER, cls.__TYPE]
        )
        tuple_list_result = wizard_filter_class.load_definition(wizard_filter_tuple_type, **kwargs)
        return tuple_list_result

    @classmethod
    def __create_instance_of_wizard_class(cls, registered_filter_wizard: dict) -> CustomFilterWizardInterface:
        return registered_filter_wizard[cls.__KEY_FOR_OBTAINING_CLASS]()

    @classmethod
    def __check_object_type(cls, wizard_filter_class: CustomFilterWizardInterface, object_type: str) -> bool:
        return object_type == wizard_filter_class.get_type_of_object()

    @classmethod
    def __cast_value(cls, value, value_type):
        if value_type == 'integer':
            return int(value)
        elif value_type == 'string':
            return str(value)
        elif value_type == 'numeric':
            return float(value)
        elif value_type == 'boolean':
            cleaned_value = cls.__remove_unexpected_chars(value)
            if cleaned_value.lower() == 'true':
                return True
            elif cleaned_value.lower() == 'false':
                return False
        elif value_type == 'date':
            # Perform date parsing logic here
            # Assuming you have a specific date format, you can use datetime.strptime
            # Example: return datetime.strptime(value, '%Y-%m-%d').date()
            pass

        # Return None if the value type is not recognized
        return None

    @classmethod
    def __remove_unexpected_chars(cls, string):
        # Define the pattern for unwanted characters
        pattern = r'[^\w\s]'  # Remove any character that is not alphanumeric or whitespace

        # Use re.sub() to remove the unwanted characters
        cleaned_string = re.sub(pattern, '', string)

        return cleaned_string
