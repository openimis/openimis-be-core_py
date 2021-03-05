import decimal
import json
import logging
import re
import sys
from datetime import datetime as py_datetime
from typing import Optional

import graphene
import graphene_django_optimizer as gql_optimizer
from core import ExtendedConnection
from core.tasks import openimis_mutation_async
from django import dispatch
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.http import HttpRequest
from django.utils import translation
from graphene.utils.str_converters import to_snake_case
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField

from .apps import CoreConfig
from .models import ModuleConfiguration, FieldControl, MutationLog, Language

from .gql_queries import *

MAX_SMALLINT = 32767
MIN_SMALLINT = -32768

core = sys.modules["core"]

logger = logging.getLogger(__name__)


class SmallInt(graphene.Int):
    """
    This represents a small Integer, with values ranging from -32768 to +32767
    """

    @staticmethod
    def coerce_int(value):
        res = super().coerce_int(value)
        if MIN_SMALLINT <= res <= MAX_SMALLINT:
            return res
        else:
            return None

    serialize = coerce_int
    parse_value = coerce_int

    @staticmethod
    def parse_literal(ast):
        result = graphene.Int.parse_literal(ast)
        if result is not None and MIN_SMALLINT <= result <= MAX_SMALLINT:
            return result
        else:
            return None


MAX_TINYINT = 255
MIN_TINYINT = 0


class TinyInt(graphene.Int):
    """
    This represents a tiny Integer (8 bit), with values ranging from 0 to 255
    """

    @staticmethod
    def coerce_int(value):
        res = super().coerce_int(value)
        if MIN_TINYINT <= res <= MAX_TINYINT:
            return res
        else:
            return None

    serialize = coerce_int
    parse_value = coerce_int

    @staticmethod
    def parse_literal(ast):
        result = graphene.Int.parse_literal(ast)
        if result is not None and MIN_TINYINT <= result <= MAX_TINYINT:
            return result
        else:
            return None


class OpenIMISJSONEncoder(DjangoJSONEncoder):
    def default(self, o):
        if isinstance(o, HttpRequest):
            if o.user:
                return f"HTTP_user: {o.user.id}"
            else:
                return None
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)


_mutation_signal_params = ["user", "mutation_module",
                           "mutation_class", "mutation_log_id", "data"]
signal_mutation = dispatch.Signal(providing_args=_mutation_signal_params)
signal_mutation_module_validate = {}
signal_mutation_module_before_mutating = {}
signal_mutation_module_after_mutating = {}

for module in sys.modules:
    signal_mutation_module_validate[module] = dispatch.Signal(providing_args=_mutation_signal_params)
    signal_mutation_module_before_mutating[module] = dispatch.Signal(providing_args=_mutation_signal_params)
    signal_mutation_module_after_mutating[module] = \
        dispatch.Signal(providing_args=_mutation_signal_params + ["error_messages"])


class OpenIMISMutation(graphene.relay.ClientIDMutation):
    """
    This class is the generic Mutation for openIMIS. It will save the mutation content into the MutationLog,
    submit it to validation, perform the potentially asynchronous mutation itself and update the MutationLog status.
    """
    class Meta:
        abstract = True

    internal_id = graphene.Field(graphene.String)

    class Input:
        client_mutation_label = graphene.String(max_length=255, required=False)
        client_mutation_details = graphene.List(graphene.String)

    @classmethod
    def async_mutate(cls, user, **data) -> Optional[str]:
        """
        This method has to be overridden in the subclasses to implement the actual mutation.
        The response should contain a boolean for success and an error message that will be saved into the DB
        :param user: contains the logged user or None
        :param data: all parameters passed to the mutation
        :return: error_message if None is returned, the response is considered to be a success
        """
        pass

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        mutation_log = MutationLog.objects.create(
            json_content=json.dumps(data, cls=OpenIMISJSONEncoder),
            user_id=info.context.user.id if info.context.user else None,
            client_mutation_id=data.get('client_mutation_id'),
            client_mutation_label=data.get("client_mutation_label"),
            client_mutation_details=json.dumps(data.get(
                "client_mutation_details"), cls=OpenIMISJSONEncoder) if data.get("client_mutation_details") else None
        )
        logging.debug("OpenIMISMutation: saved as %s, label: %s", mutation_log.id, mutation_log.client_mutation_label)
        if info and info.context and info.context.user and info.context.user.language:
            lang = info.context.user.language
            if isinstance(lang, Language):
                translation.activate(lang.code)
            else:
                translation.activate(lang)

        try:
            logging.debug("[OpenIMISMutation %s] Sending signals", mutation_log.id)
            results = signal_mutation.send(
                sender=cls, mutation_log_id=mutation_log.id, data=data, user=info.context.user,
                mutation_module=cls._mutation_module, mutation_class=cls._mutation_class)
            results.extend(signal_mutation_module_validate[cls._mutation_module].send(
                sender=cls, mutation_log_id=mutation_log.id, data=data, user=info.context.user,
                mutation_module=cls._mutation_module, mutation_class=cls._mutation_class
            ))
            errors = [err for r in results for err in r[1]]
            logging.debug("[OpenIMISMutation %s] signals sent, got errors back: ", mutation_log.id, len(errors))
            if errors:
                mutation_log.mark_as_failed(json.dumps(errors))
                return cls(internal_id=mutation_log.id)

            signal_mutation_module_before_mutating[cls._mutation_module].send(
                sender=cls, mutation_log_id=mutation_log.id, data=data, user=info.context.user,
                mutation_module=cls._mutation_module, mutation_class=cls._mutation_class
            )
            logging.debug("[OpenIMISMutation %s] before mutate signal sent", mutation_log.id)
            if core.async_mutations:
                logging.debug("[OpenIMISMutation %s] Sending async mutation", mutation_log.id)
                openimis_mutation_async.delay(
                    mutation_log.id, cls._mutation_module, cls._mutation_class)
            else:
                logging.debug("[OpenIMISMutation %s] mutating...", mutation_log.id)
                try:
                    error_messages = cls.async_mutate(
                        info.context.user if info.context and info.context.user else None,
                        **data)
                    if not error_messages:
                        logging.debug("[OpenIMISMutation %s] marked as successful", mutation_log.id)
                        mutation_log.mark_as_successful()
                    else:
                        errors_json = json.dumps(error_messages)
                        logging.debug("[OpenIMISMutation %s] marked as failed: %s", mutation_log.id, errors_json)
                        mutation_log.mark_as_failed(errors_json)
                except BaseException as exc:
                    error_messages = exc
                    logger.error("async_mutate threw an exception. It should have gotten this far.", exc_info=exc)
                    # Record the failure of the mutation but don't include details for security reasons
                    mutation_log.mark_as_failed(f"The mutation threw a {type(exc)}, check logs for details")
                logging.debug("[OpenIMISMutation %s] send post mutation signal", mutation_log.id)
                signal_mutation_module_after_mutating[cls._mutation_module].send(
                    sender=cls, mutation_log_id=mutation_log.id, data=data, user=info.context.user,
                    mutation_module=cls._mutation_module, mutation_class=cls._mutation_class,
                    error_messages=error_messages
                )
        except Exception as exc:
            logger.warning(f"Exception while processing mutation id {mutation_log.id}", exc_info=True)
            mutation_log.mark_as_failed(exc)

        return cls(internal_id=mutation_log.id)


class FieldControlGQLType(DjangoObjectType):
    class Meta:
        model = FieldControl


class ModuleConfigurationGQLType(DjangoObjectType):
    class Meta:
        model = ModuleConfiguration


class OrderedDjangoFilterConnectionField(DjangoFilterConnectionField):
    """
    Adapted from https://github.com/graphql-python/graphene/issues/251
    And then adapted by Alok Ramteke on my (Eric Darchis)' stackoverflow question:
    https://stackoverflow.com/questions/57478464/django-graphene-relay-order-by-orderingfilter/61543302
    Substituting:
    `mutation_logs = DjangoFilterConnectionField(MutationLogGQLType)`
    with:
    ```
    mutation_logs = OrderedDjangoFilterConnectionField(MutationLogGQLType,
        orderBy=graphene.List(of_type=graphene.String))
    ```
    """

    @classmethod
    def orderBy(cls, qs, args):
        order = args.get('orderBy', None)
        if order:
            if type(order) is str:
                if order == "?":
                    snake_order = RawSQL("NEWID()", params=[])
                else:
                    snake_order = to_snake_case(order)
            else:
                snake_order = [
                    to_snake_case(o) if o != "?" else RawSQL(
                        "NEWID()", params=[])
                    for o in order
                ]
            qs = qs.order_by(*snake_order)
        return qs

    @classmethod
    def resolve_queryset(
            cls, connection, iterable, info, args, filtering_args, filterset_class
    ):
        qs = super(DjangoFilterConnectionField, cls).resolve_queryset(
            connection, iterable, info, args
        )
        filter_kwargs = {k: v for k, v in args.items() if k in filtering_args}
        qs = filterset_class(data=filter_kwargs, queryset=qs, request=info.context).qs

        return OrderedDjangoFilterConnectionField.orderBy(qs, args)


class MutationLogGQLType(DjangoObjectType):
    """
    This represents a requested mutation and its status.
    The "user" search filter is only available for super-users. Otherwise, the user is automatically set to the
    currently logged user.
    """

    class Meta:
        model = MutationLog
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "client_mutation_id": ["exact"],
            "client_mutation_label": ["exact"],
            "request_date_time": ["exact", "gte", "lte"],
            "status": ["exact", "gte"],
            "user": ["exact"],
        }
        connection_class = ExtendedConnection

    status = graphene.Field(graphene.Int,
                            description=", ".join([f"{pair[0]}: {pair[1]}" for pair in MutationLog.STATUS_CHOICES]))

    @classmethod
    def get_queryset(cls, queryset, info):
        if info.context.user.is_anonymous:
            return queryset.none()
        elif info.context.user.is_superuser:
            return queryset
        else:
            queryset = queryset.filter(user=info.context.user)
        return queryset


class Query(graphene.ObjectType):
    module_configurations = graphene.List(
        ModuleConfigurationGQLType,
        validity=graphene.String(),
        layer=graphene.String())

    mutation_logs = OrderedDjangoFilterConnectionField(
        MutationLogGQLType, orderBy=graphene.List(of_type=graphene.String))

    role = OrderedDjangoFilterConnectionField(
        RoleGQLType, orderBy=graphene.List(of_type=graphene.String), validity=graphene.Date()
    )

    role_right = OrderedDjangoFilterConnectionField(
        RoleRightGQLType, orderBy=graphene.List(of_type=graphene.String), validity=graphene.Date()
    )

    modules_permissions = graphene.Field(
        ModulePermissionsListGQLType,
    )

    def resolve_role(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_roles_perms):
            raise PermissionError("Unauthorized")
        return gql_optimizer.query(Role.objects.filter(*filter_validity(**kwargs)), info)

    def resolve_role_right(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_roles_perms):
            raise PermissionError("Unauthorized")
        return gql_optimizer.query(RoleRight.objects.filter(*filter_validity(**kwargs)), info)

    def resolve_modules_permissions(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_roles_perms):
            raise PermissionError("Unauthorized")
        excluded_app = [
            "health_check.cache", "health_check", "health_check.db",
            "test_without_migrations", "test_without_migrations",
            "rules", "graphene_django", "rest_framework", "rest_framework_rules",
            "health_check.storage", "channels"
        ]
        all_apps = [app for app in settings.INSTALLED_APPS if not app.startswith("django") and app not in excluded_app]
        config = []
        for app in all_apps:
            apps = __import__(f"{app}.apps")
            if hasattr(apps.apps, 'DEFAULT_CFG'):
                config_dict = ModuleConfiguration.get_or_default(f"{app}", apps.apps.DEFAULT_CFG)
                permission = []
                for key, value in config_dict.items():
                    if "gql_query" in key or "gql_mutation" in key:
                        permission.append(PermissionOpenImisGQLType(
                            perms_name=key,
                            perms_value=value,
                        ))

                config.append(ModulePermissionGQLType(
                    module_name=app,
                    permissions=permission,
                ))
        return ModulePermissionsListGQLType(list(config))

    def resolve_module_configurations(self, info, **kwargs):
        validity = kwargs.get('validity')
        # configuration is loaded before even the core module
        # the datetime is ALWAYS a Gregorian one
        # (whatever datetime is used in business modules)
        if validity is None:
            validity = py_datetime.now()
        else:
            d = re.split('\D', validity)
            validity = py_datetime(*[int('0' + x) for x in d][:6])
        # is_exposed indicates wherever a configuration
        # is safe to be accessible from api
        # DON'T EXPOSE (backend) configurations that contain credentials,...
        crits = (
            Q(is_disabled_until=None) | Q(is_disabled_until__lt=validity),
            Q(is_exposed=True)
        )
        layer = kwargs.get('layer')
        if layer is not None:
            crits = (*crits, Q(layer=layer))
        return ModuleConfiguration.objects.prefetch_related('controls').filter(*crits)


class RoleBase:
    id = graphene.Int(required=False, read_only=True)
    uuid = graphene.String(required=False)
    name = graphene.String(required=True, max_length=50)
    alt_language = graphene.String(required=False, max_length=50)
    is_system = graphene.Int(required=True)
    is_blocked = graphene.Boolean(required=True)
    # field to save all chosen rights to the role
    rights_id = graphene.List(graphene.Int, required=False)


def update_or_create_role(data, user):
    if "client_mutation_id" in data:
        data.pop('client_mutation_id')
    if "client_mutation_label" in data:
        data.pop('client_mutation_label')
    role_uuid = data.pop('uuid') if 'uuid' in data else None
    rights_id = data.pop('rights_id') if "rights_id" in data else None
    if role_uuid:
        role = Role.objects.get(uuid=role_uuid)
        role.save_history()
        [setattr(role, k, v) for k, v in data.items()]
        role.save()
        if rights_id is not None:
            # reset all role rights assigned to the chosen role
            from core import datetime
            now = datetime.datetime.now()
            role_rights_currently_assigned = RoleRight.objects.filter(role_id=role.id)
            role_rights_currently_assigned.update(validity_to=now)
            role_rights_currently_assigned = role_rights_currently_assigned.values_list('right_id', flat=True)
            for right_id in rights_id:
                if right_id not in role_rights_currently_assigned:
                    # create role right because it is a new role right
                    RoleRight.objects.create(
                        **{
                            "role_id": role.id,
                            "right_id": right_id,
                            "audit_user_id": role.audit_user_id,
                            "validity_from": now,
                        }
                    )
                else:
                    # set date valid to - None
                    role_right = RoleRight.objects.get(Q(role_id=role.id, right_id=right_id))
                    role_right.validity_to = None
                    role_right.save()
    else:
        role = Role.objects.create(**data)
        # create role rights for that role if they were passed to mutation
        if rights_id:
            [RoleRight.objects.create(
                **{
                    "role_id": role.id,
                    "right_id": right_id,
                    "audit_user_id": role.audit_user_id,
                    "validity_from": data['validity_from'],
                   }
            ) for right_id in rights_id]
        return role
    return role


class CreateRoleMutation(OpenIMISMutation):
    """
    Create a new role, with its chosen role right
    """
    _mutation_module = "core"
    _mutation_class = "CreateRoleMutation"

    class Input(RoleBase, OpenIMISMutation.Input):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError("mutation.authentication_required")
            if not user.has_perms(CoreConfig.gql_mutation_create_roles_perms):
                raise PermissionDenied("unauthorized")
            if not user.has_perms(CoreConfig.gql_mutation_create_roles_perms):
                raise PermissionDenied("unauthorized")
            from core.utils import TimeUtils
            data['validity_from'] = TimeUtils.now()
            data['audit_user_id'] = user.id_for_audit
            update_or_create_role(data, user)
            return None
        except Exception as exc:
            return [
                {
                    'message': "core.mutation.failed_to_create_role",
                    'detail': str(exc)
                }]


class UpdateRoleMutation(OpenIMISMutation):
    """
    Update a new role, with its chosen role right
    """
    _mutation_module = "core"
    _mutation_class = "UpdateRoleMutation"

    class Input(RoleBase, OpenIMISMutation.Input):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError("mutation.authentication_required")
            if not user.has_perms(CoreConfig.gql_mutation_update_roles_perms):
                raise PermissionDenied("unauthorized")
            if 'uuid' not in data:
                raise ValidationError("There is no uuid in updateMutation input!")
            data['audit_user_id'] = user.id_for_audit
            update_or_create_role(data, user)
            return None
        except Exception as exc:
            return [
                {
                    'message': "core.mutation.failed_to_create_role",
                    'detail': str(exc)
                }]


class Mutation(graphene.ObjectType):
    create_role = CreateRoleMutation.Field()
    update_role = UpdateRoleMutation.Field()
