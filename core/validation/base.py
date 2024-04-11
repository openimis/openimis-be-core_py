from abc import ABC
from typing import Type

from core.models import HistoryModel, VersionedModel
from django.dispatch import receiver
from django.db.models.signals import pre_save
from django.db import models
from datetime import timedelta, datetime as py_datetime

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
        for f in  instance._meta.get_fields():
            if hasattr(f,'default') and not f.default == models.fields.NOT_PROVIDED and not getattr(instance, f.name):
                setattr(instance, f.name, f.default() if callable(f.default) else f.default )
            elif isinstance(f, models.DecimalField) and f.decimal_places and getattr(instance, f.name):
                setattr(instance, f.name, f"{{:.{f.decimal_places}f}}".format(float(getattr(instance, f.name))))
            elif isinstance(f, models.IntegerField) and isinstance(getattr(instance, f.name), str):
                setattr(instance, f.name, int(getattr(instance, f.name)))
            elif isinstance(f, models.DateField) and isinstance(getattr(instance, f.name), str):
                setattr(instance, f.name, py_datetime.strptime(getattr(instance, f.name)[:10], "%Y-%m-%d"))   
            elif isinstance(f, models.DateTimeField) and isinstance(getattr(instance, f.name), str):
                setattr(instance, f.name, py_datetime.strptime(getattr(instance, f.name), "%Y-%m-%dT%H:%M:%S"))   

    
        instance.full_clean(validate_unique=False)