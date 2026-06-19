from datetime import datetime as py_datetime
from copy import copy
from dirtyfields import DirtyFieldsMixin
from django.core.exceptions import ValidationError
from django.db.models import (
    Q, UUIDField, DateTimeField, BooleanField, Model, IntegerField, BigAutoField, JSONField,
)
from simple_history.models import HistoricalRecords
from core.utils import CachedManager, CachedModelMixin, filter_validity as core_filter_validity, uuidv7, get_original_user
from simple_history.utils import get_history_manager_for_model
import datetime as base_datetime


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

    def save(self, *args, user=None, silent=False, **kwargs):
        original_user = get_original_user()
        if original_user:
            user = original_user
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
        elif not silent:
            raise ValidationError(
                "Record has not be updated - there are no changes in fields"
            )
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


class OpenIMISModelMixin(Model):
    """Reusable fields and filter logic for new-style OpenIMIS models.

    Provides active/json_ext/date_deactivated + the active-based filter_validity
    and filter_queryset.

    Can be combined with OpenIMISHistoryMixin on models that want the new fields
    but need to keep a custom PK (e.g. ClaimItem, ClaimService, ClaimDedRem).
    """

    active = BooleanField(default=True)
    json_ext = JSONField(db_column="Json_ext", blank=True, null=True)
    date_deactivated = DateTimeField(null=True, default=None)
    @classmethod
    def filter_validity(cls, arg="validity", prefix="", **kwargs):
        validity = kwargs.get(arg, None)
        has_deleted = hasattr(cls, "is_deleted")
        has_active = hasattr(cls, "active") and not callable(cls.active)
        
        if not validity:
            if has_deleted:
                return [Q(is_deleted=False)]
            elif has_active:
                return [Q(active=True)]
            else:
                return [Q()]
            
        else:
            if has_deleted:
                # we assume that the last update was the deletion
                return [Q(is_deleted=True) | Q(date_updated__gte=validity) ]
            elif has_active:
                 return [Q(active=False) | Q(date_deactivated__gte=validity)]
            else:
                return [Q()]
            
           

    @classmethod
    def filter_queryset(cls, queryset=None):
        if queryset is None:
            queryset = cls.objects.filter(active=True)
        queryset = queryset.filter(active=True)
        return queryset

    class Meta:
        abstract = True


class OpenIMISModel(OpenIMISHistoryMixin, OpenIMISModelMixin):

    objects = HistoryCacheManager()    
    id = BigAutoField(
        primary_key=True, auto_created=True, editable=False
    )
    uuid = UUIDField(
        unique=True, db_column="UUID", default=uuidv7, editable=False
    )

    def set_uuid(self):
        self.uuid = uuidv7

    def set_pk(self):
        # done automatically
        pass

    class Meta:
        abstract = True


class ValidityMixin(Model):
    date_valid_from = DateTimeField(db_column="DateValidFrom", default=py_datetime.now)
    date_valid_to = DateTimeField(db_column="DateValidTo", blank=True, null=True)
    replacement_uuid = UUIDField(db_column="ReplacementUUID", blank=True, null=True)

    # to help migration from versionned model
    @property
    def validity_to(self):
        return self.date_valid_to

    @validity_to.setter
    def validity_to(self, value):
        self.date_valid_to = value

    @property
    def validity_from(self):
        return self.date_valid_from

    @validity_from.setter
    def validity_from(self, value):
        self.date_valid_from = value

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
        # replace the fields if there are any to update in new entity
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

class LegacyValidityMixin(Model):
    """Temporary mixin for models still in the migration bridge phase.

    Provides the old validity_from/validity_to fields and the old-style
    filter_validity (delegating to core_filter_validity).
    Use this + OpenIMISHistoryMixin + OpenIMISModelMixin for tables
    that are not yet fully migrated off the type-2 validity pattern.
    """

    validity_from = DateTimeField(db_column="ValidityFrom", default=py_datetime.now)
    validity_to = DateTimeField(db_column="ValidityTo", blank=True, null=True)

    @staticmethod
    def filter_validity(arg="validity", prefix="", **kwargs):
        return core_filter_validity(arg, prefix, **kwargs)

    class Meta:
        abstract = True
 
class OpenIMISBusinessModel(OpenIMISModel, ValidityMixin):
    class Meta:
        abstract = True

class OpenIMISBusinessMigrationModel(OpenIMISModel, LegacyValidityMixin, ValidityMixin):
    class Meta:
        abstract = True


class OpenIMISMigrationModel(OpenIMISModel, LegacyValidityMixin):
    """
    Temporary base class used when migrating a legacy VersionedModel (or UUIDVersionedModel)
    to the new OpenIMIS* models + django-simple-history.

    How to use (for Claim example):
    1. In the target module (e.g. claim/models.py):
       - Change `class Claim(VersionedModel, ...)` to `class Claim(OpenIMISMigrationModel):`
       - Comment out the explicit `id = ...` and `uuid = ...` declarations.
       - Remove ExtendableModel (new base already provides json_ext + other fields).
    2. Run `python manage.py makemigrations claim`
       - This produces schema changes (add active/json_ext/date_deactivated/version,
         alter id/uuid/validity_*, remove legacy_id, + creates HistoricalClaim).
    3. Create an empty data migration:
       `python manage.py makemigrations claim --name to_history --empty`
    4. In the empty migration, use:
       from core.utils import migrate_from_versioned_to_history
       RunPython that does pre-clean of dependents for soft-deleted rows,
       then migrate_from_versioned_to_history(Claim, HistoricalClaim)
    5. Switch the model base from OpenIMISMigrationModel to OpenIMISModel (or OpenIMISBusinessModel).
    6. Run makemigrations again to drop the temporary validity_from/validity_to columns
       (and legacy fields if any remain).

    Important code changes during/after migration:
    - Replace direct `validity_to__...` / `validity_from__...` filters with the model helper.
      Signature:
          Model.filter_validity(arg="validity", prefix="", **kwargs)
      - Pass `validity=<date>` to evaluate validity as of a specific date
        (omitted → "current" records).
      - Use `prefix="..."` when the model with the validity fields is **not** the
        root model of the queryset (common when joining through a relation).

      Examples:
        # Current records
        Claim.objects.filter(*Claim.filter_validity())

        # As of a given date
        Claim.objects.filter(*Claim.filter_validity(validity=some_date))

        # Validity check on a related model (e.g. the main queryset is not Claim)
        OtherModel.objects.filter(
            *Claim.filter_validity(prefix="claim__")
        )
        # inside Q
        Q(...) | Q(*Claim.filter_validity(prefix="claim__"))

        # For child tables
        Claim.objects.filter(*ClaimItem.filter_validity(prefix="items__"))

      You can also do:
        qs = Claim.filter_queryset(qs)
        qs = qs.filter(*Claim.filter_validity())

      Note: `OpenIMISMigrationModel.filter_validity()` (bridge) delegates to the
      legacy implementation and returns a list of Q objects. After you switch to
      plain `OpenIMISModel`, the same call returns a Q that works with `filter(...)`.
    - Remove or update any custom save_history() / save() overrides on the model —
      the parent OpenIMISHistoryMixin (plus simple-history) handles versioning and history creation.
    - In data-migration scripts (the "to_history" step) raw `validity_to__isnull=False`
      (or `.exclude(*Model.filter_validity())`) is still acceptable when you deliberately
      need the archived rows.
    - After switching the base class and commenting out the explicit `id`, you will likely see
      Django warnings like:
        (models.W042) Auto-created primary key used when not defining a primary key type...
      Fix by adding to your AppConfig (e.g. ClaimConfig):
        default_auto_field = 'django.db.models.BigAutoField'
      (Avoid putting it in model Meta if your project still supports Django < 3.2.)
      This tells Django your app uses BigAutoField (matching the id field provided by
      OpenIMISMigrationModel / OpenIMISModel).

    See core/migrations/0032_*, 0033_to_history.py and 0034_* for the reference execution on InteractiveUser.
    """
    class Meta:
        abstract = True
