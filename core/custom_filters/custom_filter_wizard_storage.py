import logging

from collections import namedtuple
from typing import List

from core.custom_filters.custom_filter_registry_point import CustomFilterRegistryPoint
from core.custom_filters import CustomFilterWizardInterface


logger = logging.getLogger(__name__)


class CustomFilterWizardStorage:
    """
        Class responsible for keeping information how to create filter based on the context of
        particular wizard creator. Such hub provides the information about the way how to build
        filters for chosen field.
        __KEY_FOR_OBTAINING_CLASS - constant which indicates which element from registry points should be
        considered in order to retrieve information about registered CustomFilterWizard class
        __FIELD - constant which identifies the first value of final output (tuple) how to build filter
        __FILTER - constant which identifies the second value of final output (tuple) how to build filter
        __VALUE - constant which identifies the third value of final output (tuple) how to build filter
    """

    __KEY_FOR_OBTAINING_CLASS = 'class_reference'
    __FIELD = 'field'
    __FILTER = 'filter'
    __VALUE = 'value'

    @classmethod
    def build_output_how_to_build_filter(cls, module_name: str, object_type: str, **kwargs) -> List[namedtuple]:
        """
            Building the final outcome how to build filter based on the information provided
            by registered custom filter wizard based on the provided module name and type of object.
            The output is simply the list of named tuple (from collections package). Such named
            tuple is built in such way:
            <Type>(field=<str>, filter=<str>, value=<str>) for example:
            BenefitPlan(field='income', filter='lt, gte, icontains, exact', value='')

            :param module_name: the name of module that is installed in openIMIS which is necessary
             to retrieve information about possible ways of building filters for that specific module
            :param object_type: the name of object type that is needed to retrieve information
             about possible ways of building filters for that specific type

            :return: List[namedtupe]
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
            Method responsible for running loading definition of possible ways of
            building filters in the specific provided custom filter wizard class.

            :param wizard_filter_class: dictionary which cointains the information
             about particular registered CustomWizardClass where there is implemented method
             how to load such definitions of possbile way of building filters
            :param output_of_possible_filters: the list that contains the definitions
             how to build filters. In that context is appended to such list if there are any
             specific definitions of filters for particular field.

            :return: None (void method)
        """
        wizard_filter_tuple_type = namedtuple(
            wizard_filter_class.get_type_of_object(),
            [cls.__FIELD, cls.__FILTER, cls.__VALUE]
        )
        tuple_list_result = wizard_filter_class.load_definition(wizard_filter_tuple_type, **kwargs)
        output_of_possible_filters.extend(tuple_list_result)

    @classmethod
    def __create_instance_of_wizard_class(cls, registered_filter_wizard: dict) -> CustomFilterWizardInterface:
        """
            Method responsible to create instance of custom filter wizard class

            :param registered_filter_wizard: dictionary which cointains the information
             about particular registered CustomWizardClass

            :return: bool
        """
        return registered_filter_wizard[cls.__KEY_FOR_OBTAINING_CLASS]()

    @classmethod
    def __check_object_type(cls, wizard_filter_class: CustomFilterWizardInterface, object_type: str) -> bool:
        """
            Verify if such object is matched to the object definied in instance of class responsible for
            implementing wizard interface in given object type

            :param wizard_filter_class: the instance of class responsible for implementation of
             CustomFilterWizardInterface in given object type
            :param object_type: string representation of object class that take a part in
             filtering customization.

            :return: bool
        """
        return object_type == wizard_filter_class.get_type_of_object()
