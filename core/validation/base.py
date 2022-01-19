from abc import ABC
from typing import Type

from core.models import HistoryModel


class BaseModelValidation(ABC):
    """
    Base validation class, by default all operations are unconditionally allowed.
    Validation methods should raise ValidationError in case of any data inconsistencies.
    """

    @property
    def OBJECT_TYPE(self) -> Type[HistoryModel]:
        """
        Django ORM model. It's expected that it'll be inheriting from HistoryModel.
        """
        raise NotImplementedError("Class has to define OBJECT_TYPE for service.")

    @classmethod
    def validate_create(cls, user, **data):
        pass

    @classmethod
    def validate_update(cls, user, **data):
        pass

    @classmethod
    def validate_delete(cls, user, **data):
        pass
