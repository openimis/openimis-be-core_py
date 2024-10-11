import uuid
import logging
from copy import copy
from datetime import datetime as py_datetime
import datetime as base_datetime
from dirtyfields import DirtyFieldsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from simple_history.models import HistoricalRecords
#from core.datetimes.ad_datetime import datetime as py_datetime

from ..fields import DateTimeField
from .user import User

logger = logging.getLogger(__name__)


class HistoryModelManager(models.Manager):
    """
        Custom manager that allows querying HistoryModel by uuid
    """

    def get_queryset(self):
        return super().get_queryset().annotate(uuid=F('id'))


class HistoryModel(DirtyFieldsMixin, models.Model):
    id = models.UUIDField(primary_key=True, db_column="UUID", default=None, editable=False)
    objects = HistoryModelManager()
    is_deleted = models.BooleanField(db_column="isDeleted", default=False)
    json_ext = models.JSONField(db_column="Json_ext", blank=True, null=True)
    date_created = DateTimeField(db_column="DateCreated", null=True, default=py_datetime.now)
    date_updated = DateTimeField(db_column="DateUpdated", null=True, default=py_datetime.now)
    user_created = models.ForeignKey(User, db_column="UserCreatedUUID", related_name='%(class)s_user_created',
                                     on_delete=models.deletion.DO_NOTHING, null=False)
    user_updated = models.ForeignKey(User, db_column="UserUpdatedUUID", related_name='%(class)s_user_updated',
                                     on_delete=models.deletion.DO_NOTHING, null=False)
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

    def save(self, *args, user=None, username=None, **kwargs):
        # get the user data so as to assign later his uuid id in fields user_updated etc
        if not user:
            if username:
                user = User.objects.get(username=username)
            else:
                raise ValidationError('Save error! Provide user or the username of the current user in `username` argument')
        now = py_datetime.now()
        # check if object has been newly created
        if self.id is None:
            # save the new object
            self.set_pk()
            self.user_created = user
            self.user_updated = user
            self.date_created = now
            self.date_updated = now
            return super(HistoryModel, self).save(*args, **kwargs)
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
                    raise ValidationError('Record has not be updated - the version don\'t match with existing record')
            self.date_updated = now
            self.user_updated = user
            self.version = self.version + 1
            # check if we have business model
            if hasattr(self, "replacement_uuid"):
                if self.replacement_uuid is not None and 'replacement_uuid' not in self.get_dirty_fields():
                    raise ValidationError('Update error! You cannot update replaced entity')
            return super(HistoryModel, self).save(*args, **kwargs)
        else:
            raise ValidationError('Record has not be updated - there are no changes in fields')

    def delete_history(self):
        pass

    def delete(self, *args, user=None, username=None, **kwargs):
        if not user:
            if username:
                user = User.objects.get(username=username)
            else:
                raise ValidationError('Save error! Provide user or the username of the current user in `username` argument')
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
                replaced_entity = self.__class__.objects.filter(replacement_uuid=self.id).first()
                if replaced_entity:
                    replaced_entity.replacement_uuid = None
                    replaced_entity.save(username="admin")
            return super(HistoryModel, self).save(*args, **kwargs)
        else:
            raise ValidationError(
                'Record has not be deactivating, the object is different and must be updated before deactivating')

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
    replacement_uuid = models.UUIDField(db_column="ReplacementUUID", blank=True, null=True)

    def replace_object(self, data, **kwargs):
        # check if object was created and saved in database (having date_created field)
        if self.id is None:
            return None
        user = User.objects.get(**kwargs)
        # 1 step - create new entity
        new_entity = self._create_new_entity(user=user, data=data)
        # 2 step - update the fields for the entity to be replaced
        self._update_replaced_entity(user=user, uuid_from_new_entity=new_entity.id,
                                     date_valid_from_new_entity=new_entity.date_valid_from)

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
            data.pop('uuid')
        if len(data) > 0:
            [setattr(new_entity, key, data[key]) for key in data]
        if self.date_valid_from is None:
            raise ValidationError('Field date_valid_from should not be empty')
        new_entity.save(username=user.username)
        return new_entity

    def _update_replaced_entity(self, user, uuid_from_new_entity, date_valid_from_new_entity):
        """2 step - update the fields for the entity to be replaced"""
        # convert to datetime if the date_valid_from from new entity is date
        if not isinstance(date_valid_from_new_entity, base_datetime.datetime):
            date_valid_from_new_entity = base_datetime.combine(
                date_valid_from_new_entity,
                base_datetime.min.time()
            )
        if not self.is_dirty(check_relationship=True):
            if self.date_valid_to is not None:
                if date_valid_from_new_entity < self.date_valid_to:
                    self.date_valid_to = date_valid_from_new_entity
            else:
                self.date_valid_to = date_valid_from_new_entity
            self.replacement_uuid = uuid_from_new_entity
            self.save(username=user.username)
            return self
        else:
            raise ValidationError("Object is changed - it must be updated before being replaced")

    class Meta:
        abstract = True

