import ast
import json
import logging
import uuid
from importlib import import_module
from typing import Any, Dict, Type

import core
import graphene
import jsonschema
from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import FileResponse
from django.utils.translation import gettext as _
from graphql import GraphQLError
from password_validator import PasswordValidator
from zxcvbn import zxcvbn
import datetime
logger = logging.getLogger(__file__)

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
]


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
    validity = datetime.datetime(validity.year, validity.month, validity.day, 23, 59, 59)
    return [
        Q(**{f"{prefix}validity_from__lte": validity}),
        Q(**{f"{prefix}validity_to__isnull": True}) | Q(**{f"{prefix}validity_to__gte": validity}),
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
    default_filter = kwargs.get("applyDefaultValidityFilter", False)
    date_valid_from = kwargs.get("dateValidFrom__Gte", None)
    date_valid_to = kwargs.get("dateValidTo__Lte", None)
    filters = []
    # check if we can use default filter validity
    if date_valid_from is None and date_valid_to is None:
        if default_filter:
            filters = [*filter_validity_business_model(**kwargs)]
        else:
            filters = []
    else:
        filters = [*filter_validity_business_model(**kwargs)]
    return filters


def flatten_dict(d, parent_key="", sep="_"):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
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
    RoleRight = apps.get_model("core", "RoleRight")
    Role = apps.get_model("core", "Role")
    existing_roles = Role.objects.filter(
        is_system=system_role, validity_to__isnull=True
    )
    if not existing_roles:
        logger.warning(
            "Migration requested a role_right for system role %s but couldn't find that role",
            system_role,
        )
    else:

        for existing_role in existing_roles:
            role_rights = RoleRight.objects.filter(
                role=existing_role, right_id=right_id
            ).first()
            if not role_rights:
                RoleRight.objects.create(
                    role=existing_role,
                    right_id=right_id,
                    validity_from=datetime.datetime.now()
                )



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
            {"message": _("core.utils.schema_validation.invalid_schema") % {"error": str(schema_error)}}
        ]
    except ValueError as json_error:
        return [
            {"message": _("core.utils.schema_validation.invalid_json") % {"error": str(json_error)}}
        ]


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
