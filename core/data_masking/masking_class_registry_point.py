import logging

from typing import List


logger = logging.getLogger(__name__)


class MaskingClassRegistryPoint:

    REGISTERED_MASKING_CLASS = []

    @classmethod
    def register_masking_class(
        cls,
        masking_class_list
    ) -> None:
        for masking_class in masking_class_list:
            cls.__collect_mask_class(masking_class)

    @classmethod
    def __collect_mask_class(
        cls,
        masking_class
    ) -> None:
        cls.REGISTERED_MASKING_CLASS.append({
            "class_reference": masking_class,
            "name": masking_class.__class__.__name__,
            "model": masking_class.masking_model
        })
