import logging

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
    def build_output_how_to_build_filter(cls, module_name: str, object_type: str, **kwargs) -> List[namedtuple]:
        """
            Build the final outcome for creating a filter based on the information provided by
            a registered custom filter wizard for the specified module name and object type.

            The output is a list of named tuples (from the collections package). Each named tuple is built
            in the following format: <Type>(field=<str>, filter=<str>, value=<str>)

            Example named tuple: BenefitPlan(field='income', filter='lt, gte, icontains, exact', value='')

            Args:
                module_name (str): The name of the module installed in openIMIS, required to retrieve information
                                   about the possible ways of building filters for that specific module.
                object_type (str): The name of the object type for which the filter building information is needed.

            Returns:
                List[namedtuple]: A list of named tuples representing the final outcome for creating a filter.
        """
        output_of_possible_filters = []
        registered_filter_wizards = CustomFilterRegistryPoint.REGISTERED_CUSTOM_FILTER_WIZARDS
        if module_name in registered_filter_wizards:
            for registered_filter_wizard in registered_filter_wizards[module_name]:
                if cls.__KEY_FOR_OBTAINING_CLASS in registered_filter_wizard:
                    wizard_filter_class = cls.__create_instance_of_wizard_class(registered_filter_wizard)
                    if cls.__check_object_type(wizard_filter_class, object_type):
                        cls.__run_load_definition_object_in_wizard(wizard_filter_class, output_of_possible_filters, **kwargs)
        return output_of_possible_filters

    @classmethod
    def __run_load_definition_object_in_wizard(
        cls,
        wizard_filter_class: CustomFilterWizardInterface,
        output_of_possible_filters: List[namedtuple],
        **kwargs
    ) -> None:
        """
        Run the loading of definitions for possible ways of building filters in the provided
        custom filter wizard class.

        Args:
            wizard_filter_class (CustomFilterWizardInterface): An instance of the custom filter wizard class
                                                              responsible for loading filter definitions.
            output_of_possible_filters (list): A list that contains the definitions of how to build filters.
                                              Any specific definitions for a particular field will be appended
                                              to this list.

        Returns:
            None: This is a void method.
        """
        wizard_filter_tuple_type = namedtuple(
            wizard_filter_class.get_type_of_object(),
            [cls.__FIELD, cls.__FILTER, cls.__TYPE]
        )
        tuple_list_result = wizard_filter_class.load_definition(wizard_filter_tuple_type, **kwargs)
        output_of_possible_filters.extend(tuple_list_result)

    @classmethod
    def __create_instance_of_wizard_class(cls, registered_filter_wizard: dict) -> CustomFilterWizardInterface:
        """
        Create an instance of the custom filter wizard class.

        Args:
            registered_filter_wizard (dict): A dictionary containing information about the particular
                                             registered CustomWizardClass.

        Returns:
            CustomFilterWizardInterface: An instance of the custom filter wizard class.
        """
        return registered_filter_wizard[cls.__KEY_FOR_OBTAINING_CLASS]()

    @classmethod
    def __check_object_type(cls, wizard_filter_class: CustomFilterWizardInterface, object_type: str) -> bool:
        """
        Verify if the object is matched to the object defined in the instance of the class responsible for
        implementing the wizard interface in the given object type.

        Args:
            wizard_filter_class (CustomFilterWizardInterface): An instance of the class responsible for
                                                              implementing the CustomFilterWizardInterface
                                                              in the given object type.
            object_type (str): The string representation of the object class that takes part in filtering customization.

        Returns:
            bool: True if the object is matched, False otherwise.
        """
        return object_type == wizard_filter_class.get_type_of_object()
