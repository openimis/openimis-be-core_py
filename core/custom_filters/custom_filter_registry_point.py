import logging
import os

from typing import List

from core.custom_filters import CustomFilterWizardInterface


logger = logging.getLogger(__name__)


class CustomFilterRegistryPoint:
    """
    Class responsible for handling the registration of custom filters.

    REGISTERED_CUSTOM_FILTER_WIZARDS:
    A dictionary that collects registered implementations of custom filter wizards.
    The structure of the dictionary is as follows:

    {
        'policy': [],
        'social_protection': [
            {
                'class_reference': <class 'social_protection.custom_filters.BeneficiaryCustomFilterCreator'>,
                'module': 'social_protection'
            }
        ]
    }
    """

    REGISTERED_CUSTOM_FILTER_WIZARDS = {}

    @classmethod
    def register_custom_filters(
        cls,
        module_name: str,
        custom_filter_class_list: List[CustomFilterWizardInterface]
    ) -> None:
        """
            Register custom filter wizards for a specific module in the openIMIS application.

            This method registers the provided list of objects as custom filters in the hub,
            for the specified module in the openIMIS application.

            Args:
                module_name (str): The name of the module installed in openIMIS.
                custom_filter_class_list (list): A list of objects representing the custom filter implementations.

            Returns:
                None: This method does not return anything.
        """
        logger.debug(F"registering custom filter in {module_name} module")
        for custom_filter_class in custom_filter_class_list:
            cls.__collect_custom_filter_wizards(module_name, custom_filter_class)
            logger.debug(F"Such module {module_name} provides custom filters wizards")

    @classmethod
    def __collect_custom_filter_wizards(
        cls,
        module_name: str,
        custom_filter_class: CustomFilterWizardInterface
    ) -> None:
        """
            Gather the presence of a custom filter wizard class in a specific module and register it.

            This method checks the presence of a custom filter wizard class within the module.
            If the class exists, the filter wizard reference is added to the list of registered wizards
            within the openIMIS application.

            Args:
                module_name (str): The name of the module from which the custom filter objects originate.
                custom_filter_class: An object that needs to be registered as a custom filter in the hub,
                                     grouped under the specific module.

            Returns:
                None: This is a void method.
        """
        if module_name not in cls.REGISTERED_CUSTOM_FILTER_WIZARDS:
            cls.REGISTERED_CUSTOM_FILTER_WIZARDS[f"{module_name}"] = []
        cls.REGISTERED_CUSTOM_FILTER_WIZARDS[f"{module_name}"].append({
            "class_reference": custom_filter_class,
            "module": module_name
        })
