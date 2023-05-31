import inspect
import importlib
import importlib.util
import logging
import os


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
    def register_custom_filters(cls, module_name: str) -> None:
        """
            Process registering the custom filters wizards for
            particular module registered in openIMIS applicatiom

            :param module_name: the name of module that is installed in openIMIS.
            :return: None (void method)
        """
        logger.debug(F"registering custom filter in {module_name} module")
        if cls.__check_module_file(module_name, 'custom_filters.py'):
            cls.__collect_custom_filter_wizards(module_name)
            logger.debug(F"Such module {module_name} provides custom filters wizards")
        else:
            logger.debug(f"Such module {module_name} doesn't provide any custom filters wizards")

    @classmethod
    def __check_module_file(cls, module_name: str, file_name: str) -> bool:
        """
            Verify if module contains particular file responsible for
            registering custom filter wizard

            :param module_name: the name of module that is installed in openIMIS
             where we need to check the file presence.
            :param file_name: the name of file that we need to check if this file
             is included in that particular module.
            :return: bool
        """
        try:
            module_path = __import__(module_name).__file__
            file_path = os.path.join(os.path.dirname(module_path), file_name)
            return os.path.isfile(file_path)
        except ModuleNotFoundError:
            logger.debug(f"{module_name} does not exist within openIMIS application")
            return False
        except Exception as exc:
            logger.debug(f"{module_name}: unknown exception occurred during registering custom filter: {exc}")
            return False

    @classmethod
    def __collect_custom_filter_wizards(cls, module_name: str) -> None:
        """
            Gathering the presence of custom filter wizard class in particular module
            There is additional check whether there is such kind of class within custom_filter.py
            file. If yes then such filter wizard reference is added to the list of registered wizards
            within openIMIS application

            :param module_name: the name of module that is installed in openIMIS
             where it is checked if there is filter wizard implementation.
            :return: None (void method)
        """
        cls.REGISTERED_CUSTOM_FILTER_WIZARDS[f"{module_name}"] = []
        for class_name, class_object in inspect.getmembers(
            importlib.import_module(f"{module_name}.custom_filters"),
            inspect.isclass
        ):
            source_of_wizard_class = class_object.__module__.split('.')[0]
            if (
                module_name == source_of_wizard_class and
                cls.__CLASS_SUBSTRING_NAME in class_name
            ):
                cls.REGISTERED_CUSTOM_FILTER_WIZARDS[f"{module_name}"].append({
                    "class_name": class_name,
                    "class_reference": class_object,
                    "module": module_name
                })
