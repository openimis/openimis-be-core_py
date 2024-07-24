import logging

from core.data_masking.masking_class_registry_point import MaskingClassRegistryPoint

logger = logging.getLogger(__name__)


class MaskingClassStorage:

    @classmethod
    def get_masking_class(cls, masking_model: str):
        masking_class = None
        for method_info in MaskingClassRegistryPoint.REGISTERED_MASKING_CLASS:
            if method_info['model'] == masking_model:
                masking_class = method_info['class_reference']
        return masking_class
