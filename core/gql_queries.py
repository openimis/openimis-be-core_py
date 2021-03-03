import graphene
from core import ExtendedConnection, filter_validity
from graphene_django import DjangoObjectType

from core.models import Officer, Role, RoleRight, UserRole

from .utils import prefix_filterset


class OfficerGQLType(DjangoObjectType):
    class Meta:
        model = Officer
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "uuid": ["exact"],
            "code": ["exact", "icontains"],
            "last_name": ["exact", "icontains"],
            "other_names": ["exact", "icontains"],
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        queryset = queryset.filter(*filter_validity())
        return queryset


class RoleGQLType(DjangoObjectType):
    class Meta:
        model = Role
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "name": ["exact", "istartswith", "icontains", "iexact"],
            "is_system": ["exact"],
            "is_blocked": ["exact"],
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        if info.context.user.is_anonymous:
            return queryset.none()
        elif info.context.user.is_superuser:
            return queryset
        else:
            queryset = queryset.filter(*filter_validity())
        return queryset


class RoleRightGQLType(DjangoObjectType):
    class Meta:
        model = RoleRight
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "right_id": ["exact"],
            **prefix_filterset("role__", RoleGQLType._meta.filter_fields),
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        if info.context.user.is_anonymous:
            return queryset.none()
        elif info.context.user.is_superuser:
            return queryset
        else:
            queryset = queryset.filter(*filter_validity())
        return queryset


class PermissionOpenImisGQLType(graphene.ObjectType):
    perms_name = graphene.String()
    perms_value = graphene.String()


class ModulePermissionGQLType(graphene.ObjectType):
    module_name = graphene.String()
    permissions = graphene.List(PermissionOpenImisGQLType)


class ModulePermissionsListGQLType(graphene.ObjectType):
    module_perms_list = graphene.List(ModulePermissionGQLType)
