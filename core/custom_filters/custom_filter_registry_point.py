import logging
import os

from typing import List

from core.custom_filters import CustomFilterWizardInterface


logger = logging.getLogger(__name__)


class CustomFilterRegistryPoint:
    """
        Class reponsible for delivering methods to handle registering custom filters.
        REGISTERED_CUSTOM_FILTER_WIZARDS - dictionary responsible for collecting registered implementation of custom
        filter wizards. The example of structure is:
          {
              'policy': [],
              'social_protection': [{
                'class_name': 'BeneficiaryCustomFilterCreator',
                'class_reference': <class 'social_protection.custom_filters.BeneficiaryCustomFilterCreator'>,
                'module': 'social_protection'
            }]
          }
        __CLASS_SUBSTRING_NAME - constant responsible for checking if particual module contains
        implementation of custom filter. The fixed value is 'CustomFilterWizard'.
    """

    REGISTERED_CUSTOM_FILTER_WIZARDS = {}

    __CLASS_SUBSTRING_NAME = "CustomFilterWizard"

    @classmethod
    def register_custom_filters(
        cls,
        module_name: str,
        custom_filter_class_list: List[CustomFilterWizardInterface]
    ) -> None:
        """
            Process registering the custom filters wizards for
            particular module registered in openIMIS applicatiom

            :param module_name: the name of module that is installed in openIMIS.
            :param custom_filter_class_list: list of objects that need to be registered as a custom filter in hub.
            :return: None (void method)
        """
        logger.debug(F"registering custom filter in {module_name} module")
        for custom_filter_class in custom_filter_class_list:
            cls.__collect_custom_filter_wizards(module_name, custom_filter_class)
            logger.debug(F"Such module {module_name} provides custom filters wizards")

    @classmethod
    def __collect_custom_filter_wizards(cls, module_name: str, custom_filter_class: CustomFilterWizardInterface) -> None:
        """
            Gathering the presence of custom filter wizard class in particular module
            There is additional check whether there is such kind of class within custom_filter.py
            file. If yes then such filter wizard reference is added to the list of registered wizards
            within openIMIS application

            :param module_name: the name of module that is installed in openIMIS
             where it is checked if there is filter wizard implementation.
            :param custom_filter_class: object that need to be registered as a custom filter in hub
            :return: None (void method)
        """
        cls.REGISTERED_CUSTOM_FILTER_WIZARDS[f"{module_name}"] = []
        cls.REGISTERED_CUSTOM_FILTER_WIZARDS[f"{module_name}"].append({
            "class_reference": custom_filter_class,
            "module": module_name
        })
