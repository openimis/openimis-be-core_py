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
    """

    __KEY_FOR_OBTAINING_CLASS = 'class_reference'
    __FIELD = 'field'
    __FILTER = 'filter'
    __VALUE = 'value'

    @classmethod
    def build_output_for_frontend(cls) -> List[namedtuple]:
        output_of_possible_filters = []
        registered_filter_wizards = CustomFilterRegistryPoint.REGISTERED_CUSTOM_FILTER_WIZARDS
        for key in registered_filter_wizards:
            for registered_filter_wizard in registered_filter_wizards[key]:
                if cls.__KEY_FOR_OBTAINING_CLASS:
                    wizard_filter_class = cls.__create_instance_of_wizard_class(registered_filter_wizard)
                    cls.__run_load_definition_object_in_wizard(wizard_filter_class, output_of_possible_filters)
                    logger.debug('Definiton has been loaded into output')
                else:
                    logger.debug('There is no information about class representation for wizard filters')
        return output_of_possible_filters

    @classmethod
    def __run_load_definition_object_in_wizard(
        cls,
        wizard_filter_class: CustomFilterWizardInterface,
        output_of_possible_filters: List[namedtuple]
    ) -> None:
        wizard_filter_tuple_type = namedtuple(
            wizard_filter_class.get_type_of_object(),
            [cls.__FIELD, cls.__FILTER, cls.__VALUE]
        )
        tuple_result = wizard_filter_class.load_definition(wizard_filter_tuple_type)
        output_of_possible_filters.append(tuple_result)

    @classmethod
    def __create_instance_of_wizard_class(cls, registered_filter_wizard) -> CustomFilterWizardInterface:
        return registered_filter_wizard[cls.__KEY_FOR_OBTAINING_CLASS]()
