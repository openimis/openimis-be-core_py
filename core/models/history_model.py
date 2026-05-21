import logging
from copy import copy
from datetime import datetime as py_datetime
from django.core.cache import caches
import datetime as base_datetime
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from dirtyfields import DirtyFieldsMixin
from core.utils import CachedManager, CachedModelMixin, uuidv7
from simple_history.utils import bulk_update_with_history, bulk_create_with_history
from django.db.models import (
    DateTimeField, Model, IntegerField,
)
from simple_history.models import HistoricalRecords
from django.apps import apps

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


class HistoryModel(DirtyFieldsMixin, CachedModelMixin, Model):
    history = HistoricalRecords(
        inherit=True,
    )
    version = IntegerField(default=1)

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
        "core.User",
        db_column="UserCreatedUUID",
        related_name="%(class)s_user_created",
        on_delete=models.deletion.DO_NOTHING,
        null=False,
    )
    user_updated = models.ForeignKey(
        "core.User",
        db_column="UserUpdatedUUID",
        related_name="%(class)s_user_updated",
        on_delete=models.deletion.DO_NOTHING,
        null=False,
    )
    version = models.IntegerField(default=1)

    @property
    def uuid(self):
        return self.id

    @uuid.setter
    def uuid(self, v):
        self.id = v

    @property
    def active(self):
        return not self.is_deleted

    @active.setter
    def active(self, value):
        self.is_deleted = not value

    def set_pk(self):
        self.pk = uuidv7()

    @classmethod
    def filter_queryset(cls, queryset=None):
        if queryset is None:
            queryset = cls.objects.filter(is_deleted=False)
        queryset = queryset.filter(is_deleted=False)
        return queryset

    @classmethod
    def bulk_save(cls, data_list, user, batch_size=100, include_deleted=False):
        """
        Efficiently update or create multiple instances based on 'id' field.
        All operations are atomic - either all succeed or all fail.

        Args:
            data_list: List of dicts with instance data (with or without 'id')
            user: User performing the operation
            batch_size: Number of records to process per batch
            include_deleted: If True, includes soft-deleted records in the lookup and allows updating the `is_deleted` field

        Returns:
            dict with 'created' and 'updated' counts
        """
        if not data_list:
            return {'created': 0, 'updated': 0}

        now = py_datetime.now()

        ids_to_update = [d['id'] for d in data_list if d.get('id')]

        query_filter = {'id__in': ids_to_update}
        if not include_deleted:
            query_filter['is_deleted'] = False
        existing = {obj.id: obj for obj in cls.objects.filter(**query_filter)}

        to_create = []
        to_update = []

        exclude_fields = {
            'id', 'uuid', 'date_created', 'user_created', 'date_updated',
            'user_updated', 'version', 'date_valid_from',
            'date_valid_to', 'replacement_uuid'
        }
        if not include_deleted:
            exclude_fields.add('is_deleted')

        for data in data_list:
            record_id = data.get('id')

            if record_id and record_id in existing:
                instance = existing[record_id]
                for field, value in data.items():
                    if field not in exclude_fields:
                        setattr(instance, field, value)
                instance.user_updated = user
                instance.date_updated = now
                instance.version = instance.version + 1
                to_update.append(instance)
            else:
                create_data = {k: v for k, v in data.items() if k not in exclude_fields}
                instance = cls(**create_data)
                instance.set_pk()
                instance.user_created = user
                instance.user_updated = user
                instance.date_created = now
                instance.date_updated = now
                instance.version = 1
                to_create.append(instance)

        with transaction.atomic():
            created_count = 0
            updated_count = 0

            if to_create:
                created = bulk_create_with_history(to_create, cls, batch_size=batch_size, default_user=user)
                cls.bulk_update_cache(created)
                created_count = len(created)

            if to_update:
                update_fields = [
                    f for f in to_update[0].__dict__.keys()
                    if not f.startswith('_') and f not in exclude_fields
                ]
                update_fields += ['user_updated', 'date_updated', 'version']
                updated_count = bulk_update_with_history(to_update, cls, update_fields, batch_size=batch_size, default_user=user)
                cls.bulk_update_cache(to_update)

        return {'created': created_count, 'updated': updated_count}

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

    def save(self, *args, user=None, username=None, **kwargs):
        # get the user data so as to assign later his uuid id in fields user_updated etc
        user = self.get_user(user=user, username=username)
        now = py_datetime.now()
        # check if object has been newly created
        if self.id is None:
            # save the new object
            self.set_pk()
            self.user_created = user
            self.date_created = now
            self.date_updated = now
            self.user_updated = user
            result = super().save(*args, **kwargs)
            self.update_cache()
            return result
        if self.is_dirty(check_relationship=True):
            if not self.user_created:
                # past = self.objects.filter(pk=self.id).first()
                # if not past:
                self.user_created = user
                self.date_created = now
                # TODO this could erase a instance, version check might be too light
                # elif not self.version == past.version:
                #     raise ValidationError(
                #         "Record has not be updated - the version don't match with existing record"
                #     )
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
            result = super().save(*args, **kwargs)
            self.update_cache()
            return result
        return None

    def delete_history(self):
        pass

    def get_user(self, user=None, username=None):
        if not user:
            user_id = 1
            if username:
                user = apps.get_model('core', 'User').objects.filter(username=username).first()
            elif getattr(self, 'audit_user_id', None):
                user_id = getattr(self, 'audit_user_id', None)
                if user_id == -1:
                    user_id = 1
            if not user:
                user = apps.get_model('core', 'User').objects.filter(i_user_id=user_id).first()
            # if not user and not settings.IS_TESTING:
            #     user = get_current_user()
        return user

    def delete(self, *args, user=None, username=None, **kwargs):
        user = self.get_user(user=user, username=username)
        if not self.is_dirty(check_relationship=True) and getattr(self, 'active', True):
            now = py_datetime.now()
            self.date_updated = now
            self.user_updated = user
            self.version = self.version + 1
            self.active = False
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
            result = super().save(*args, **kwargs)
            return result
        else:
            raise ValidationError(
                "Record has not be deactivated, the object is different and must be updated before deactivating"
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

    class Meta:
        abstract = True


class HistoryBusinessModel(HistoryModel):
    date_valid_from = DateTimeField(db_column="DateValidFrom", default=py_datetime.now)
    date_valid_to = DateTimeField(db_column="DateValidTo", blank=True, null=True)
    replacement_uuid = models.UUIDField(
        db_column="ReplacementUUID", blank=True, null=True
    )

    def replace_object(self, data, **kwargs):
        from .user import User
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
