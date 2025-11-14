import uuid
import logging
from copy import copy
from datetime import datetime as py_datetime
from django.core.cache import caches
import datetime as base_datetime
from dirtyfields import DirtyFieldsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from simple_history.models import HistoricalRecords
from core.utils import CachedManager, CachedModelMixin, get_current_user

# from core.datetimes.ad_datetime import datetime as py_datetime

from ..fields import DateTimeField
from .user import User

logger = logging.getLogger(__name__)

cache = caches["default"]


class HistoryModelManager(CachedManager):
    """
    Custom manager that allows querying HistoryModel by uuid
    and includes caching logic for better performance.
    """

    def get_queryset(self):
        return super().get_queryset().annotate(uuid=F("id"))

    def filter(self, *args, **kwargs):
        # Check if 'uuid' is in kwargs, and if so, rename it to 'id'
        if "uuid" in kwargs:
            kwargs["id"] = kwargs.pop("uuid")
        # Call the parent class's filter method with the modified kwargs
        return super().filter(*args, **kwargs)

    def get(self, *args, **kwargs):
        # Check if 'uuid' is in kwargs, and if so, rename it to 'id'
        if "uuid" in kwargs:
            kwargs["id"] = kwargs.pop("uuid")
        # Call the parent class's filter method with the modified kwargs
        return super().get(*args, **kwargs)


class HistoryModel(DirtyFieldsMixin, CachedModelMixin, models.Model):
    id = models.UUIDField(
        primary_key=True, db_column="UUID", default=None, editable=False
    )
    objects = HistoryModelManager()
    is_deleted = models.BooleanField(db_column="isDeleted", default=False)
    json_ext = models.JSONField(db_column="Json_ext", blank=True, null=True)
    date_created = DateTimeField(
        db_column="DateCreated", null=True, default=py_datetime.now
    )
    date_updated = DateTimeField(
        db_column="DateUpdated", null=True, default=py_datetime.now
    )
    user_created = models.ForeignKey(
        User,
        db_column="UserCreatedUUID",
        related_name="%(class)s_user_created",
        on_delete=models.deletion.DO_NOTHING,
        null=False,
    )
    user_updated = models.ForeignKey(
        User,
        db_column="UserUpdatedUUID",
        related_name="%(class)s_user_updated",
        on_delete=models.deletion.DO_NOTHING,
        null=False,
    )
    version = models.IntegerField(default=1)
    history = HistoricalRecords(
        inherit=True,
    )

    @property
    def uuid(self):
        return self.id

    @uuid.setter
    def uuid(self, v):
        self.id = v

    def set_pk(self):
        self.pk = uuid.uuid4()

    def save_history(self):
        pass

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        """
        Overrides the default update to update the cache after saving the instance.
        """
        obj_data = kwargs.pop("data", {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        [setattr(self, key, obj_data[key]) for key in obj_data]
        if save:
            self.save(*args, user=user, username=user, **kwargs)
        return self

    def _get_user(self, user=None, username=None):

        audit_user = get_current_user()
        if audit_user:
            return audit_user
        elif user:
            return user
        elif username:
            audit_user = User.objects.get(username=username, *User.filter_validity())
            return audit_user
        else:
            raise ValidationError(
                "Save error! Provide user or the username of the current user in `username` argument"
            )

    def save(self, *args, user=None, username=None, **kwargs):
        # get the user data so as to assign later his uuid id in fields user_updated etc
        user = self._get_user(user, username)
        now = py_datetime.now()
        # check if object has been newly created
        if self.id is None:
            # save the new object
            self.set_pk()
            self.user_created = user
            self.user_updated = user
            self.date_created = now
            self.date_updated = now
            result = super(HistoryModel, self).save(*args, **kwargs)
            self.update_cache()
            return result
        if self.is_dirty(check_relationship=True):
            if not self.user_created:
                past = self.objects.filter(pk=self.id).first()
                if not past:
                    self.user_created = user
                    self.user_updated = user
                    self.date_created = now
                    self.date_updated = now
                # TODO this could erase a instance, version check might be too light
                elif not self.version == past.version:
                    raise ValidationError(
                        "Record has not be updated - the version don't match with existing record"
                    )
            self.date_updated = now
            self.user_updated = user
            self.version = self.version + 1
            # check if we have business model
            if hasattr(self, "replacement_uuid"):
                if (
                    self.replacement_uuid is not None
                    and "replacement_uuid" not in self.get_dirty_fields()
                ):
                    raise ValidationError(
                        "Update error! You cannot update replaced entity"
                    )
            errors = super(HistoryModel, self).save(*args, **kwargs)
            if not errors:
                self.update_cache()
            return errors
        else:
            raise ValidationError(
                "Record has not be updated - there are no changes in fields"
            )

    def delete_history(self):
        pass

    def delete(self, *args, user=None, username=None, **kwargs):
        user = self._get_user(user, username)
        if not self.is_dirty(check_relationship=True) and not self.is_deleted:

            now = py_datetime.now()
            self.date_updated = now
            self.user_updated = user
            self.version = self.version + 1
            self.is_deleted = True
            # check if we have business model
            if hasattr(self, "replacement_uuid"):
                # When a replacement entity is deleted, the link should be removed
                # from replaced entity so a new replacement could be generated
                replaced_entity = self.__class__.objects.filter(
                    replacement_uuid=self.id
                ).first()
                if replaced_entity:
                    replaced_entity.replacement_uuid = None
                    replaced_entity.save(user=user)
            result = super(HistoryModel, self).save(*args, **kwargs)
            self.update_cache()
            return result
        else:
            raise ValidationError(
                "Record has not be deactivating, the object is different and must be updated before deactivating"
            )

    def copy(self, exclude_fields=["id", "uuid"]):
        """
        Creates a copy of a Django model instance, excluding specified fields (default: 'id' and 'uuid').
        Args:
            exclude_fields: List of field names to exclude from copying (default: ['id', 'uuid'])
        Returns:
            A new unsaved instance with copied attributes
        """
        model_class = self.__class__
        new_instance = model_class()
        fields = self._meta.get_fields()
        for field in fields:
            if field.name not in exclude_fields and hasattr(self, field.name):
                if field.is_relation:
                    if field.many_to_one or field.one_to_one:
                        setattr(new_instance, field.name, getattr(self, field.name))
                    elif field.one_to_many or field.many_to_many:
                        continue
                else:
                    setattr(new_instance, field.name, getattr(self, field.name))

        return new_instance

    @classmethod
    def filter_queryset(cls, queryset=None):
        if queryset is None:
            queryset = cls.objects.all()
        queryset = queryset.filter()
        return queryset

    class Meta:
        abstract = True


class HistoryBusinessModel(HistoryModel):
    date_valid_from = DateTimeField(db_column="DateValidFrom", default=py_datetime.now)
    date_valid_to = DateTimeField(db_column="DateValidTo", blank=True, null=True)
    replacement_uuid = models.UUIDField(
        db_column="ReplacementUUID", blank=True, null=True
    )

    def replace_object(self, data, **kwargs):
        # check if object was created and saved in database (having date_created field)
        if self.id is None:
            return None
        user = User.objects.get(**kwargs)
        # 1 step - create new entity
        new_entity = self._create_new_entity(user=user, data=data)
        # 2 step - update the fields for the entity to be replaced
        self._update_replaced_entity(
            user=user,
            uuid_from_new_entity=new_entity.id,
            date_valid_from_new_entity=new_entity.date_valid_from,
        )

    def _create_new_entity(self, user, data):
        """1 step - create new entity"""
        now = py_datetime.now()
        new_entity = copy(self)
        new_entity.id = None
        new_entity.version = 1
        new_entity.date_valid_from = now
        new_entity.date_valid_to = None
        new_entity.replacement_uuid = None
        # replace the fiedls if there are any to update in new entity
        if "uuid" in data:
            data.pop("uuid")
        if len(data) > 0:
            [setattr(new_entity, key, data[key]) for key in data]
        if self.date_valid_from is None:
            raise ValidationError("Field date_valid_from should not be empty")
        new_entity.save(user=user)
        return new_entity

    def _update_replaced_entity(
        self, user, uuid_from_new_entity, date_valid_from_new_entity
    ):
        """2 step - update the fields for the entity to be replaced"""
        # convert to datetime if the date_valid_from from new entity is date
        if not isinstance(date_valid_from_new_entity, base_datetime.datetime):
            date_valid_from_new_entity = base_datetime.combine(
                date_valid_from_new_entity, base_datetime.min.time()
            )
        if not self.is_dirty(check_relationship=True):
            if self.date_valid_to is not None:
                if date_valid_from_new_entity < self.date_valid_to:
                    self.date_valid_to = date_valid_from_new_entity
            else:
                self.date_valid_to = date_valid_from_new_entity
            self.replacement_uuid = uuid_from_new_entity
            self.save(user=user)
            return self
        else:
            raise ValidationError(
                "Object is changed - it must be updated before being replaced"
            )

    class Meta:
        abstract = True
