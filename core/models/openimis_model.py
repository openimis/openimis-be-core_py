from datetime import datetime as py_datetime
from dirtyfields import DirtyFieldsMixin
from django.core.exceptions import ValidationError
from django.db.models import (
    Q, UUIDField, DateTimeField, BooleanField, Model, IntegerField, BigAutoField, JSONField,
)
from simple_history.models import HistoricalRecords
from core.utils import CachedManager, CachedModelMixin, filter_validity as core_filter_validity, uuidv7
from simple_history.utils import get_history_manager_for_model


class HistoryCacheManager(CachedManager):

    exclude_fields = {
        'id', 'uuid', 'version'
    }

    def bulk_create(self, objs, user=None, **kwargs):
        now = py_datetime.now()
        for obj in objs:
            obj.set_pk()
            obj.version = 1
        updated_row = super().bulk_create(objs, **kwargs)
        self.model.bulk_update_cache(updated_row)
        history_manager = get_history_manager_for_model(self.model)
        history_manager.bulk_history_create(
            objs,
            batch_size=kwargs.get('batch_size', None),
            update=True,
            default_date=now,
            default_user=user
        )
        return updated_row

    def bulk_update(self, objs, fields, user=None, **kwargs):
        now = py_datetime.now()
        for obj in objs:
            obj.version += 1
        field_to_update = [field for field in fields if field not in self.exclude_fields] + ['version']
        super().bulk_update(objs, field_to_update, **kwargs)
        updated_count = self.model.bulk_update_cache(objs)
        history_manager = get_history_manager_for_model(self.model)
        history_manager.bulk_history_create(
            objs,
            batch_size=kwargs.get('batch_size', None),
            update=True,
            default_date=now,
            default_user=user
        )
        return updated_count


class OpenIMISHistoryMixin(DirtyFieldsMixin, CachedModelMixin, Model):
    history = HistoricalRecords(
        inherit=True,
    )
    version = IntegerField(default=1)

    def save_history(self):
        pass

    def update(self, *args, save=True, **kwargs):
        """
        Overrides the default update to update the cache after saving the instance.
        """
        obj_data = kwargs.pop("data", {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        [setattr(self, key, obj_data[key]) for key in obj_data]
        if save:
            self.save(*args, **kwargs)
        return self

    def save(self, *args, user=None, **kwargs):
        # get the user data so as to assign later his uuid id in fields
        if user:
            self._history_user = user
        # check if object has been newly created
        if self.id is None:
            # save the new object
            self.set_pk()
            result = super().save(*args, **kwargs)
            self.update_cache()
            return result
        if self.is_dirty(check_relationship=True):
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

    def delete(self, *args, user=None, **kwargs):
        if not self.is_dirty(check_relationship=True) and getattr(self, 'active', True):
            self.version = self.version + 1
            self.active = False
            if user:
                self._history_user = user
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

    @staticmethod
    def filter_validity(arg="validity", prefix="", **kwargs):
        validity = kwargs.get(arg, None)
        if not validity:
            return Q(active=True)
        else:
            return Q(active=False) | Q(date_deactivated__gte=validity)

    class Meta:
        abstract = True


class OpenIMISModel(OpenIMISHistoryMixin):

    objects = HistoryCacheManager()
    id = BigAutoField(
        primary_key=True, auto_created=True, editable=False
    )
    uuid = UUIDField(
        unique=True, db_column="UUID", default=uuidv7, editable=False
    )
    active = BooleanField(default=True)

    json_ext = JSONField(db_column="Json_ext", blank=True, null=True)
    date_deactivated = DateTimeField(null=True, default=None)

    def set_uuid(self):
        self.uuid = uuidv7

    def set_pk(self):
        # done automatically
        pass

    @classmethod
    def filter_queryset(cls, queryset=None):
        if queryset is None:
            queryset = cls.objects.filter(active=True)
        queryset = queryset.filter(active=True)
        return queryset

    class Meta:
        abstract = True


class OpenIMISMigrationModel(OpenIMISModel):
    ####
    # How to use:
    # for migration of Versionned Model to openIMIS Model
    # will keep the id as is but will rename the table column to id
    # 1. change the base model of the class you want to use by OpenIMISMigrationModel and comment id and uuid
    # 2. run `python manage.py makemigrations app_name` to update the table changes : rename and new column,
    #    it will also create the history tablesrun `python manage.py makemigrations app_name --name to_history --empty`
    # 3.
    # 4. in that migration file, run MyModel.migrate_to_history() to move all the
    #    record that have validitiy_to not null to history model
    # 5. change the base model of the class you want to use by OpenIMISModel
    # 6. run `python manage.py makemigrations app_name` to update the table changes : remove the validity_to and from
    ####
    validity_from = DateTimeField(db_column="ValidityFrom", default=py_datetime.now, null=True)
    validity_to = DateTimeField(db_column="ValidityTo", blank=True, null=True, default=None)

    @staticmethod
    def filter_validity(arg="validity", prefix="", **kwargs):
        return core_filter_validity(arg, prefix, **kwargs)

    class Meta:
        abstract = True
