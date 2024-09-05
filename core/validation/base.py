from abc import ABC
from typing import Type

from core.models import HistoryModel, VersionedModel
from django.dispatch import receiver
from django.db.models.signals import pre_save
from django.db import models
from datetime import datetime as py_datetime
import logging
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


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


# enforce object validation on every save
@receiver(pre_save)
def validator(sender, instance, **kwargs):
    if issubclass(sender, (HistoryModel, VersionedModel)):
        for f in instance._meta.get_fields():
            attr = getattr(instance, f.name) if not f.one_to_many and hasattr(instance, f.name) and not f.many_to_many else None
            if hasattr(f, 'default') and not f.default == models.fields.NOT_PROVIDED and not attr:
                setattr(instance, f.name, f.default() if callable(f.default) else f.default)
            elif attr:
                if isinstance(f, models.DecimalField) and f.decimal_places:
                    setattr(instance, f.name, f"{{:.{f.decimal_places}f}}".format(float(attr)))
                elif isinstance(f, models.IntegerField) and isinstance(attr, str):
                    setattr(instance, f.name, int(attr))
                elif isinstance(f, models.DateField) and isinstance(attr, str):
                    setattr(instance, f.name, py_datetime.strptime(attr[:10], "%Y-%m-%d"))
                elif isinstance(f, models.DateTimeField) and not isinstance(attr, py_datetime):
                    if hasattr(attr, 'to_ad_datetime'):
                        setattr(instance, f.name, attr.to_ad_datetime())
                    elif isinstance(f, models.DateTimeField) and isinstance(attr, str):
                        setattr(instance, f.name, py_datetime.strptime(attr, "%Y-%m-%dT%H:%M:%S"))
        try:
            instance.full_clean(validate_unique=False)
        except Exception as e:
            msg = f"Object {instance.__class__.__name__} is not respecting the mandatory fields: {e}"
            raise ValidationError(msg)
