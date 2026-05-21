import ast
import json
import logging
import uuid
from importlib import import_module
from typing import Any, Dict
from collections.abc import Mapping
import core
import graphene
import jsonschema
from django.db import models
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError, FieldDoesNotExist
from django.core.files.storage import default_storage
from django.db.models import Q, ForeignKey
from django.http import FileResponse
from django.utils.translation import gettext as _
from password_validator import PasswordValidator
from zxcvbn import zxcvbn
import datetime
from django.core.cache import caches
from functools import lru_cache
# utils/request_local.py
import threading
from django.db import transaction
# from simple_history.utils import update_change_reason
import time
import os


_request_local = threading.local()

logger = logging.getLogger(__file__)


cache = caches["default"]

__all__ = [
    "TimeUtils",
    "full_class_name",
    "comparable",
    "filter_validity",
    "prefix_filterset",
    "assert_string_length",
    "PATIENT_CATEGORY_MASK_MALE",
    "PATIENT_CATEGORY_MASK_FEMALE",
    "PATIENT_CATEGORY_MASK_ADULT",
    "PATIENT_CATEGORY_MASK_MINOR",
    "patient_category_mask",
    "ExtendedConnection",
    "get_scheduler_method_ref",
    "ExtendedRelayConnection",
    "subtract_date_ranges",
]


def get_current_user():
    return getattr(_request_local, "user", None)


def set_current_user(user):
    _request_local.user = user


def clear_current_user():
    if hasattr(_request_local, "user"):
        del _request_local.user


class TimeUtils(object):

    @classmethod
    def now(cls):
        return core.datetime.datetime.now()

    @classmethod
    def date(cls):
        return core.datetime.datetime.date(cls.now())


def full_class_name(o):
    module = o.__class__.__module__
    if module is None or module == str.__class__.__module__:
        return o.__class__.__name__
    return module + "." + o.__class__.__name__


def comparable(cls):
    """Class decorator providing generic comparison functionality"""

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)

    cls.__eq__ = __eq__
    cls.__ne__ = __ne__
    return cls


def filter_validity(arg="validity", prefix="", **kwargs):

    validity = kwargs.get(arg)
    if validity is None:
        return [Q(**{f"{prefix}validity_to__isnull": True})]
    elif isinstance(validity, str):
        validity = datetime.datetime.strptime(validity)
    validity = datetime.datetime(
        validity.year, validity.month, validity.day, 23, 59, 59
    )
    return [
        Q(**{f"{prefix}validity_from__lte": validity}),
        Q(**{f"{prefix}validity_to__isnull": True})
        | Q(**{f"{prefix}validity_to__gte": validity}),
    ]


def filter_validity_business_model(
    arg="dateValidFrom__Gte", arg2="dateValidTo__Lte", **kwargs
):
    date_valid_from = kwargs.get(arg)
    date_valid_to = kwargs.get(arg2)
    # default scenario
    if not date_valid_from and not date_valid_to:
        today = core.datetime.datetime.now()
        return __place_the_filters(date_start=today, date_end=None)

    # scenario - only date valid to set
    if not date_valid_from and date_valid_to:
        today = core.datetime.datetime.now()
        oldest = min([today, date_valid_to])
        return __place_the_filters(date_start=oldest, date_end=date_valid_to)

    # scenario - only date valid from
    if date_valid_from and not date_valid_to:
        return __place_the_filters(date_start=date_valid_from, date_end=None)

    # scenario - both filters set
    if date_valid_from and date_valid_to:
        return __place_the_filters(date_start=date_valid_from, date_end=date_valid_to)


def __place_the_filters(date_start, date_end):
    """funtion related to 'filter_validity_business_model'
    function so as to set up the chosen filters
    to filter the validity of the entity
    """
    if not date_end:
        return (
            Q(date_valid_from__isnull=False),
            Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=date_start),
        )
    return (
        Q(date_valid_from__lte=date_end),
        Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=date_start),
    )


def append_validity_filter(**kwargs):
    default_filter = kwargs.pop("applyDefaultValidityFilter", False)
    date_valid_from = kwargs.pop("dateValidFrom__Gte", None)
    date_valid_to = kwargs.pop("dateValidTo__Lte", None)
    filters = []
    # check if we can use default filter validity
    if date_valid_from is None and date_valid_to is None:
        if default_filter:
            filters = [*filter_validity_business_model()]
        else:
            filters = []
    else:
        filters = [*filter_validity_business_model(
            dateValidFrom__Gte=date_valid_from,
            dateValidTo__Lte=date_valid_to)
        ]

    return filters


def flatten_dict(d, parent_key="", sep="."):
    """Flatten a nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, (dict, Mapping)):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def filter_is_deleted(arg="is_deleted", **kwargs):
    is_deleted = kwargs.get(arg)
    if is_deleted is None:
        is_deleted = False
    return Q(is_deleted=is_deleted)


def prefix_filterset(prefix, filterset):
    if type(filterset) is dict:
        return {(prefix + k): v for k, v in filterset.items()}
    elif type(filterset) is list:
        return [(prefix + x) for x in filterset]
    else:
        return filterset


def assert_string_length(str_value, length):
    if length and len(str_value) > length:
        raise Exception(
            _("core.string.over_max_length")
            % {"value": str_value, "max_length": length}
        )


PATIENT_CATEGORY_MASK_MALE = 1
PATIENT_CATEGORY_MASK_FEMALE = 2
PATIENT_CATEGORY_MASK_ADULT = 4
PATIENT_CATEGORY_MASK_MINOR = 8


def patient_category_mask(insuree, target_date):
    if type(target_date) is str:
        from core import datetime

        # TODO: this should be nicer
        target_date = datetime.date(*[int(x) for x in target_date.split("-")])
    mask = 0
    if not insuree.gender:
        raise NotImplementedError(_("core.insuree.unknown_gender"))
    if not insuree.dob:
        raise NotImplementedError(_("core.insuree.unknown_dob"))

    if insuree.gender.code in ("M", "O"):
        mask = mask | PATIENT_CATEGORY_MASK_MALE
    else:
        mask = mask | PATIENT_CATEGORY_MASK_FEMALE

    if insuree.is_adult(target_date):
        mask = mask | PATIENT_CATEGORY_MASK_ADULT
    else:
        mask = mask | PATIENT_CATEGORY_MASK_MINOR
    return mask


class CachedManager(models.Manager):
    UNIQUE_FIELDS = {"pk", "id", "uuid"}
    CACHED_FK = {}

    def get(self, *args, **kwargs):
        """
        Overrides get() to use cache for single exact lookups on pk, id, or uuid.
        Returns a single instance or raises DoesNotExist/MultipleObjectsReturned.
        """
        if not getattr(self.model, "USE_CACHE", False):
            return super().get(*args, **kwargs)
        is_simple, key, value, field, lookup = self._is_simple_lookup(args, kwargs)

        if is_simple and lookup == "exact":
            # Try cache lookup for exact queries
            cache_result = self._handle_cache_lookup(field, value, lookup)
            if cache_result is not None:
                cached_qs = cache_result
                logger.debug(
                    "Cache hit for get() with key: %s",
                    get_cache_key(self.model, self._normalize_value(value)),
                )
                return list(cached_qs)[0]  # Use first() to get single instance

        # Fallback to default get() for non-simple queries or cache miss
        instance = super().get(*args, **kwargs)

        # Cache the instance for future lookups
        instance.update_cache()
        return instance

    def _normalize_value(self, value):
        """Normalize value for cache key."""
        if isinstance(value, (str, uuid.UUID)):
            return str(value).lower()
        try:
            return int(value)
        except (ValueError, TypeError):
            return value

    def _is_simple_lookup(self, args, kwargs):
        """Check if query is a single exact or in lookup on unique fields."""
        if kwargs and len(kwargs) == 1:
            key = list(kwargs.keys())[0]
            field = key.split("__")[0] if "__" in key else key
            lookup = key.split("__")[-1] if "__" in key else "exact"
            return (
                field in self.UNIQUE_FIELDS and lookup in {"exact", "in"},
                key,
                kwargs.get(key),
                field,
                lookup,
            )
        elif args and len(args) == 1 and isinstance(args[0], Q):
            if len(args[0].children) == 1 and isinstance(args[0].children[0], tuple):
                field, value = args[0].children[0]
                lookup = field.split("__")[-1] if "__" in field else "exact"
                field = field.split("__")[0]
                return (
                    field in self.UNIQUE_FIELDS and lookup in {"exact", "in"},
                    field,
                    value,
                    field,
                    lookup,
                )
            else:
                logger.debug("Complex Q object detected: %s", args[0].children)
        return False, None, None, None, None

    def _instances_to_queryset(self, instances, ordered=False):
        """Convert a list of model instances to a QuerySet without hitting the database."""
        if not instances:
            return self.get_queryset().none()
        qs = self.get_queryset().filter(pk__in=[instance.pk for instance in instances])
        if ordered:
            qs = qs.order_by("pk")
            qs._result_cache = sorted(instances, key=lambda instance: instance.pk)
        else:
            qs._result_cache = list(instances)
        return qs

    # In CachedManager, update _handle_cache_lookup for 'exact' (similar changes for 'in' below)
    def _handle_cache_lookup(self, field, value, lookup):
        """Handle cache lookup for exact or in queries."""
        if lookup == "exact":
            cache_key = get_cache_key(self.model, self._normalize_value(value))
            cached_data = cache.get(cache_key)
            if cached_data:
                if isinstance(cached_data, dict):
                    # Instantiate from dict to ensure proper __init__ and dirtyfields state
                    cached_instance = self.model(**cached_data)
                    cached_instance._state.adding = (
                        False  # Mark as not new (DB-loaded simulation)
                    )
                    if hasattr(cached_instance, "_state"):
                        cached_instance._state.db = (
                            "default"  # Optional: Set DB alias if needed
                        )

                    for fk in self.CACHED_FK:
                        get_cached_foreign_key(cached_instance, fk)
                    logger.debug("Cache hit for key: %s", cache_key)
                    return self._instances_to_queryset([cached_instance], True)
                elif isinstance(cached_data, (uuid.UUID, str)):
                    return self._handle_cache_lookup("pk", cached_data, lookup)
                else:
                    logger.error("Wrong type in cache for key: %s", cache_key)
                    return None
            return None

        if lookup == "in":
            if not isinstance(value, (list, tuple, set)):
                return None
            values = [self._normalize_value(v) for v in value]
            cache_keys = [get_cache_key(self.model, v) for v in values]
            cached_results = cache.get_many(cache_keys)
            cached_instances = []
            uncached_values = []

            for v, ck in zip(values, cache_keys):
                data = cached_results.get(ck)
                if data:
                    if isinstance(data, dict):
                        instance = self.model(**data)
                        instance._state.adding = False
                        if hasattr(instance, "_state"):
                            instance._state.db = "default"
                        for fk in self.CACHED_FK:
                            get_cached_foreign_key(instance, fk)
                        cached_instances.append(instance)
                        logger.debug("Cache hit for key: %s", ck)
                    elif isinstance(data, (uuid.UUID, str)):
                        cache_result = self._handle_cache_lookup(
                            "pk", data, "exact"
                        )  # Note: Use 'exact' for recursion
                        if cache_result:
                            cached_instances.extend(cache_result._result_cache)
                            logger.debug("Cache hit for key: %s", ck)
                        else:
                            uncached_values.append(v)
                    else:
                        logger.error("Wrong type in cache for key: %s", ck)
                        uncached_values.append(v)
                else:
                    uncached_values.append(v)

            qs = self.get_queryset().none()
            if cached_instances:
                qs = self._instances_to_queryset(cached_instances)
            return qs, uncached_values, field

        return None

    def filter(self, *args, **kwargs):
        """
        Overrides filter() to use cache for single exact or in lookups on pk, id, or uuid.
        Returns a QuerySet to support chaining without unnecessary DB queries.
        """
        if getattr(self.model, "USE_CACHE", False):
            is_simple, key, value, field, lookup = self._is_simple_lookup(args, kwargs)
        else:
            is_simple = False
        if not is_simple:
            return super().filter(*args, **kwargs)

        # Try cache lookup
        cache_result = self._handle_cache_lookup(field, value, lookup)
        if cache_result is None:
            # Fallback to default filter for invalid lookups or cache miss
            return super().filter(*args, **kwargs)

        if lookup == "exact":
            cached_qs = cache_result
            if cached_qs is not None:
                return cached_qs
            # Cache miss, query DB and cache
            qs = super().filter(*args, **kwargs)
            if qs.exists():
                instance = qs.first()
                instance.update_cache()
            return qs

        # Handle in lookup
        cached_qs, uncached_values, field = cache_result
        if uncached_values:
            db_filter = {f"{field}__in": uncached_values}
            db_qs = super().filter(**db_filter)

            db_instances = list(db_qs)
            for instance in db_instances:
                instance.update_cache()
            # Combine cached and DB instances into a single QuerySet
            if cached_qs:
                all_instances = cached_qs._result_cache + db_instances
            else:
                all_instances = db_instances
            cached_qs = self._instances_to_queryset(all_instances, True)

        return cached_qs

    def get_from_cache(self, **kwargs):
        """
        Utility method to fetch instances from cache or DB using ORM-like syntax.
        Returns a QuerySet.
        """
        is_simple, key, value, field, lookup = self._is_simple_lookup((), kwargs)
        if not is_simple:
            return None

        cache_result = self._handle_cache_lookup(field, value, lookup)
        if cache_result is None:
            return None

        if lookup == "exact":
            cached_qs = cache_result
            if cached_qs is not None:
                return cached_qs
            return None

        cached_qs, uncached_values, field = cache_result
        if uncached_values:
            return None

        return cached_qs


def get_cached_foreign_key(instance, fk_field_name):
    """
    Retrieves a ForeignKey-related object from cache for a given model instance, without querying the database.
    Args:
        instance: The model instance (e.g., User instance).
        fk_field_name: The name of the ForeignKey field (e.g., 'i_user').
    Returns:
        The cached related object or None if not in cache or invalid.
    """

    logger.debug(
        "get_cached_foreign_key called: instance=%s, fk_field_name=%s",
        instance,
        fk_field_name,
    )
    # do nothing if exists already
    # if getattr(instance, fk_field_name, None) is not None:
    #     return None
    # Get the model field
    try:
        field = instance._meta.get_field(fk_field_name)
    except FieldDoesNotExist:
        logger.error(
            "Field %s does not exist on model %s",
            fk_field_name,
            instance._meta.model_name,
        )
        return None

    # Verify it's a ForeignKey
    if not isinstance(field, ForeignKey):
        logger.error(
            "Field %s on model %s is not a ForeignKey",
            fk_field_name,
            instance._meta.model_name,
        )
        return None

    # Get the ForeignKey value (e.g., i_user_id)
    fk_value = getattr(
        instance, field.attname
    )  # attname is the column name (e.g., i_user_id)
    if fk_value is None:
        logger.debug("ForeignKey value for %s is None", fk_field_name)
        return None


def clean_fk(instance):
    """
    Returns a dictionary representation of a Django model instance
    with ForeignKey fields as _id and excluding relational fields.

    Args:
        instance: A Django model instance.

    Returns:
        dict: A dictionary containing field values suitable for model instantiation.
    """
    field_values = {}
    for field in instance._meta.get_fields():
        if not isinstance(
            field,
            (
                models.ForeignKey,
                models.ManyToOneRel,
                models.ManyToManyRel,
                models.ManyToManyField,
            ),
        ):
            field_values[field.name] = getattr(instance, field.name)
        elif getattr(instance, f"{field.name}_id", None) is not None:
            field_values[f"{field.name}_id"] = getattr(instance, f"{field.name}_id")
    return field_values


def uuidv7() -> uuid.UUID:
    """
    Generate a UUIDv7.
    """
    # random bytes
    value = bytearray(os.urandom(16))

    # current timestamp in ms
    timestamp = int(time.time() * 1000)

    # timestamp
    value[0] = (timestamp >> 40) & 0xFF
    value[1] = (timestamp >> 32) & 0xFF
    value[2] = (timestamp >> 24) & 0xFF
    value[3] = (timestamp >> 16) & 0xFF
    value[4] = (timestamp >> 8) & 0xFF
    value[5] = timestamp & 0xFF

    # version and variant
    value[6] = (value[6] & 0x0F) | 0x70
    value[8] = (value[8] & 0x3F) | 0x80

    return uuid.UUID(bytes=bytes(value))


class CachedModelMixin:
    USE_CACHE = settings.CACHE_OBJECT_DEFAULT
    UNIQUE_FIELDS = {"id", "uuid", "pk"}

    @classmethod
    def bulk_update_cache(cls, objs):
        """
        Efficiently update caches for a list of updated objects after bulk_update.
        Call this manually after your manager's bulk_update if needed,
        or integrate into the manager method.
        """
        if not cls.USE_CACHE or not objs:
            return

        now = settings.CACHE_OBJECT_TTL  # or None for no timeout

        # Get unique fields once
        unique_fields = getattr(cls, "UNIQUE_FIELDS")

        # Primary caches: key(pk) -> full cleaned object
        primary_data = {}
        for obj in objs:
            if obj.pk:
                primary_data[get_cache_key(cls, obj.pk)] = clean_fk(obj)

        if primary_data:
            cache.set_many(primary_data, timeout=now)

        # Secondary caches: key(field_value) -> pk  (only if value != pk)
        secondary_data = {}
        for obj in objs:
            if not obj.pk:
                continue
            for f in unique_fields:
                try:
                    val = getattr(obj, f)
                except AttributeError:
                    continue  # skip if field doesn't exist (e.g. property)
                if val != obj.pk:  # your original condition
                    key = get_cache_key(cls, val)
                    secondary_data[key] = obj.pk

        if secondary_data:
            cache.set_many(secondary_data, timeout=now)

        logger.debug("Bulk cached %d instances of %s", len(objs), cls.__name__)

    def update_cache(self):
        """
        Updates the cache for this object after saving.
        """
        if self.USE_CACHE:
            cache.set(
                get_cache_key(self.__class__, self.pk),
                clean_fk(self),
                timeout=settings.CACHE_OBJECT_TTL,
            )
            unique_fields = getattr(
                self, "UNIQUE_FIELDS", {"id", "uuid", "pk"}
            )
            for f in unique_fields:
                # get_field raised an error on property raise
                if self.pk != getattr(self, f, self.pk):
                    cache.set(
                        get_cache_key(self.__class__, getattr(self, f)),
                        self.pk,
                        timeout=settings.CACHE_OBJECT_TTL,
                    )
            logger.debug("Saved and cached instance: %s", self)

    def delete_cache(self):
        """
        Deletes the cache entry for this object.
        """
        if self.USE_CACHE:
            cache_key = f"{self.__class__.__name__}:{self.pk}"
            cache.delete(cache_key)
            logger.debug(f"Removed instance from cache: {cache_key}")

    class Meta:
        abstract = True


class ExtendedConnection(graphene.Connection):
    """
    Adds total_count and edge_count to Graphene connections. To use, simply add to the
    Graphene object definition Meta:
    `connection_class = ExtendedConnection`
    """

    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            raise PermissionDenied(_("unauthorized"))
        return self.length

    def resolve_edge_count(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            raise PermissionDenied(_("unauthorized"))
        return len(self.edges)


def block_update(update_dict, current_object, attribute_name, Ex=ValueError):
    if attribute_name in update_dict and update_dict["code"] != getattr(
        current_object, attribute_name
    ):
        raise Ex("That {attribute_name} field is not editable")


def get_scheduler_method_ref(name):
    """
    Use to retrieve the method reference from a str name. This is necessary when the module cannot be imported from
    that location.
    :param name: claim.module.submodule.method or similar name
    :return: reference to the method
    """
    split_name = name.split(".")
    module = __import__(".".join(split_name[:-1]))
    for subitem in split_name[1:]:
        module = getattr(module, subitem)
    return module


class ExtendedRelayConnection(graphene.relay.Connection):
    """
    Adds total_count and edge_count to Graphene Relay connections.
    """
    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(self, info, **kwargs):
        return len(self.iterable)

    def resolve_edge_count(self, info, **kwargs):
        return len(self.edges)


def get_first_or_default_language():
    from core.models import Language

    sorted_languages = Language.objects.filter(sort_order__isnull=False)
    if sorted_languages.exists():
        return sorted_languages.order_by("sort_order").first()
    else:
        return Language.objects.first()


def insert_role_right_for_system(system_role, right_id, apps):
    pass
    # do not manage the role and right via migrations
    # RoleRight = apps.get_model("core", "RoleRight")
    # Role = apps.get_model("core", "Role")
    # existing_roles = Role.objects.filter(
    #     is_system=system_role, validity_to__isnull=True
    # )
    # if not existing_roles:
    #     logger.warning(
    #         "Migration requested a role_right for system role %s but couldn't find that role",
    #         system_role,
    #     )
    # else:
    #     for existing_role in existing_roles:
    #         role_rights = RoleRight.objects.filter(
    #             role=existing_role, right_id=right_id
    #         ).first()
    #         if not role_rights:
    #             RoleRight.objects.create(
    #                 role=existing_role,
    #                 right_id=right_id,
    #                 validity_from=datetime.datetime.now(),
    #             )


def remove_role_right_for_system(system_role, right_id, apps):
    RoleRight = apps.get_model("core", "RoleRight")
    Role = apps.get_model("core", "Role")
    existing_roles = Role.objects.filter(
        is_system=system_role, validity_to__isnull=True
    )
    if not existing_roles:
        logger.warning(
            "Migration requested to remove a role_right for system role %s but couldn't find that role",
            system_role,
        )
    for existing_role in existing_roles:
        role_rights = RoleRight.objects.filter(role=existing_role, right_id=right_id)
        if not role_rights:
            logger.warning(
                "Role right not found for system role %s and right ID %s",
                system_role,
                right_id,
            )
        for role_right in role_rights:
            role_right.delete()
            logger.info(
                "Role right removed for system role %s and right ID %s",
                system_role,
                right_id,
            )


def convert_to_python_value(string):
    try:
        value = ast.literal_eval(string)
        return value
    except (SyntaxError, ValueError):
        return string


def is_valid_uuid(string):
    try:
        uuid.UUID(str(string))
        return True
    except ValueError:
        return False


def validate_json_schema(schema):
    try:
        if not isinstance(schema, dict):
            schema = json.loads(schema)
        jsonschema.Draft7Validator.check_schema(schema)
        return []
    except jsonschema.exceptions.SchemaError as schema_error:
        return [
            {
                "message": _("core.utils.schema_validation.invalid_schema")
                % {"error": str(schema_error)}
            }
        ]
    except ValueError as json_error:
        return [
            {
                "message": _("core.utils.schema_validation.invalid_json")
                % {"error": str(json_error)}
            }
        ]


def to_json_safe_value(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


class CustomPasswordValidator:
    def __init__(self, uppercase=0, lowercase=0, digits=0, symbols=0):
        self.schema = PasswordValidator()
        self.requirements = {
            "PASSWORD_UPPERCASE": "uppercase",
            "PASSWORD_LOWERCASE": "lowercase",
            "PASSWORD_DIGITS": "digits",
            "PASSWORD_SYMBOLS": "symbols",
        }
        self.set_password_policy()

    def set_password_policy(self):
        self.schema.min(settings.PASSWORD_MIN_LENGTH)
        for setting, method in self.requirements.items():
            if getattr(settings, setting) > 0:
                getattr(self.schema.has(), method)()

    def validate(self, password, user=None):
        if not self.schema.validate(password):
            raise ValidationError(self.get_help_text())
        zxcvbn_result = zxcvbn(password)
        if zxcvbn_result["score"] < 3:
            raise ValidationError(
                "Password is too weak. Avoid common patterns and dictionary words."
            )

    def get_help_text(self):
        return (
            f"Your password must be at least {settings.PASSWORD_MIN_LENGTH} characters long, "
            f"contain at least {settings.PASSWORD_UPPERCASE} uppercase letter(s), "
            f"{settings.PASSWORD_LOWERCASE} lowercase letter(s), "
            f"{settings.PASSWORD_DIGITS} number(s), and "
            f"{settings.PASSWORD_SYMBOLS} special character(s)."
        )


class DefaultStorageFileHandler:
    def __init__(self, file_path):
        self.file_path = file_path

    def save_file(self, file):
        self.check_file_path()
        default_storage.save(self.file_path, file)
        file.seek(0)

    def remove_file(self):
        if default_storage.exists(self.file_path):
            default_storage.delete(self.file_path)

    def get_file_content(self):
        if not default_storage.exists(self.file_path):
            raise FileNotFoundError("File does not exist at the specified path.")
        with default_storage.open(self.file_path, "rb") as source:
            return source.read()

    def get_file_response_csv(self, file_name=None):
        if not default_storage.exists(self.file_path):
            raise FileNotFoundError("File does not exist at the specified path.")
        response = FileResponse(default_storage.open(self.file_path, "rb"))
        response["Content-Type"] = "text/csv"
        response["Content-Disposition"] = (
            f'attachment; filename="{file_name if file_name else "default.csv"}"'
        )
        return response

    def check_file_path(self):
        if default_storage.exists(self.file_path):
            raise FileExistsError("File already exists at the specified path.")

    @staticmethod
    def list_files(directory):
        """
        Get a list of files in the specified directory within default storage.
        """
        return default_storage.listdir(directory)


class ConfigUtilMixin:
    @classmethod
    def _load_config_fields(cls, default_cfg: Dict[str, Any]):
        """
        Load all config fields that match current AppConfig class fields, all custom fields have to be loaded separately
        """
        for field in default_cfg:
            if hasattr(cls, field):
                setattr(cls, field, default_cfg[field])

    @classmethod
    def _load_config_function(cls, function_name, path):
        """
        Load a function specified as module path into config.
        Example:
        "core.apps.function" will be loaded as "from core.apps import function" and assigned as "cls.function_name"
        """
        try:
            mod, name = path.rsplit(".", 1)
            if not mod or not name:
                raise ImportError(
                    "Invalid function path, module and function name are required"
                )
            module = import_module(mod)
            function = getattr(module, name)
            setattr(cls, function_name, function)
        except ImportError as e:
            logger.error(
                "Failed to configure function '%s' as '%s.%s': %s",
                path,
                cls.__name__,
                function_name,
                str(e),
            )


def clear_cache(instance):
    cache.delete(get_cache_key(instance.__class__, instance.pk))


def get_cache_key(model, id):
    return f"cs_{model.__name__}_{str(id).lower()}"


def is_this_session_superuser(session_key):
    from django.contrib.sessions.models import Session
    from django.utils.timezone import now
    from core.models import User

    try:
        session = Session.objects.get(session_key=session_key, expire_date__gte=now())
        data = session.get_decoded()
        user_id = data.get("_auth_user_id")
        if user_id:
            user = User.objects.get(id=user_id)
            if user.is_superuser:
                return True
    except Session.DoesNotExist:
        pass
    except Exception:
        pass

    return False


@lru_cache(maxsize=1)
def collect_all_gql_permissions():
    """
    Collect all GQL permission codes from Django app configs into a dict structure:
    {app: {perm_name: [perm_ids]}}.
    Scans for attributes in DEFAULT_CFG or DEFAULT_CONFIG ending with '_perms' that are lists.
    """
    excluded_apps = [
        "health_check.cache",
        "health_check",
        "health_check.db",
        "test_without_migrations",
        "rules",
        "graphene_django",
        "rest_framework",
        "health_check.storage",
        "channels",
        "graphql_jwt.refresh_token.apps.RefreshTokenConfig",
    ]
    all_apps = [
        app
        for app in settings.INSTALLED_APPS
        if not app.startswith("django") and app not in excluded_apps
    ]

    permissions_dict = {}
    for app in all_apps:
        try:
            app_module = __import__(f"{app}.apps")
            config_dict = None
            if hasattr(app_module.apps, "DEFAULT_CFG"):
                config_dict = flatten_dict(app_module.apps.DEFAULT_CFG)
            elif hasattr(app_module.apps, "DEFAULT_CONFIG"):
                config_dict = flatten_dict(app_module.apps.DEFAULT_CONFIG)

            if config_dict:
                app_perms = {}
                for key, value in config_dict.items():
                    if key.endswith("_perms") and isinstance(value, list):
                        app_perms[key] = [str(perm) for perm in value]
                if app_perms:  # Only add apps with permissions
                    permissions_dict[app] = app_perms
        except (ImportError, AttributeError):
            continue

    return permissions_dict


@lru_cache(maxsize=1)
def to_list_permissions():
    """Convert collected permissions to a set of all permission IDs."""
    permissions_dict = collect_all_gql_permissions()
    all_perms = set()
    for app_perms in permissions_dict.values():
        for perm_ids in app_perms.values():
            for perm_id in perm_ids:
                all_perms.add(int(perm_id))
    return sorted(list(all_perms))


def migrate_from_versioned_to_history(model_class, history_model_class):
    """
    Migrates records with non-null validity_to to the history model for the given model class.

    Args:
        model_class: The Django model class to migrate (e.g., InteractiveUser).
        history_model_class: The corresponding history model class (e.g., HistoricalInteractiveUser).

    Returns:
        str: A message indicating the number of records migrated.
    """
    records_to_migrate = model_class.objects.filter(validity_to__isnull=False)
    migrated_count = 0

    with transaction.atomic():
        for record in records_to_migrate:
            try:
                # Create a history record
                history_record = history_model_class()

                # Copy all fields from the original record
                for field in record._meta.get_fields():
                    if field.name not in ['history']:  # Skip id and history fields
                        if field.is_relation:
                            if field.many_to_one or field.one_to_one:
                                try:
                                    setattr(history_record, field.name, getattr(record, field.name))
                                except Exception as e:
                                    logger.warning(f"Failed to copy relation field {field.name}: {e}")
                        else:
                            setattr(history_record, field.name, getattr(record, field.name))

                # Set history-specific fields
                history_record.history_date = record.validity_to or datetime.datetime.now()
                history_record.history_change_reason = "Migrated to history"
                history_record.history_type = '~'  # Update operation

                # Save the history record
                history_record.save()

                # Update change reason
                # update_change_reason(history_record, "Migrated to history")

                # Delete the original record from the main table
                record.delete()
                migrated_count += 1

            except Exception as e:
                logger.error(f"Error migrating record {record.id}: {e}")
                raise

    result = f"Migrated {migrated_count} records to history for {model_class.__name__}"
    logger.info(result)
    return result


def subtract_date_ranges(main_range, date_ranges):
    from core import to_date

    main_start = to_date(main_range[0])
    main_end = to_date(main_range[1])
    result = []
    current = main_start

    sorted_ranges = sorted(date_ranges, key=lambda x: to_date(x[0]))

    for start, end in sorted_ranges:
        start = to_date(start)
        end = to_date(end)
        if current < start:
            result.append((current, min(start, main_end)))

        current = max(current, end)

        if current >= main_end:
            break

    if current < main_end:
        result.append((current, main_end))

    return result
