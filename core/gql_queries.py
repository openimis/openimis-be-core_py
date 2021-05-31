import graphene
from core import ExtendedConnection, filter_validity
from graphene_django import DjangoObjectType

from core.models import Officer, Role, RoleRight, UserRole, User, InteractiveUser

from .utils import prefix_filterset


class OfficerGQLType(DjangoObjectType):
    """
    This type corresponds to the Enrolment Officer but is a bit more generic than just Enrolment.
    """
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
            "uuid": ["exact"],
            "name": ["exact", "istartswith", "icontains", "iexact"],
            "is_blocked": ["exact"],
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return Role.get_queryset(queryset, info)


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
        return RoleRight.get_queryset(queryset, info)


class InteractiveUserGQLType(DjangoObjectType):
    """
    The InteractiveUser represents the regular openIMIS allowed to connect to the web interface. Enrolment Officers
    and Claim Administrators can exist without having web access but when they do, they have a corresponding
    InteractiveUser, linked by their "code" aka "login_name"
    """
    class Meta:
        model = InteractiveUser
        interfaces = (graphene.relay.Node,)
        exclude = ("stored_password", "private_key")
        filter_fields = {
            "id": ["exact"],
            "uuid": ["exact"],
            "last_name": ["icontains"],
            "other_names": ["icontains"],
            "phone": ["iexact"],
            "login_name": ["iexact"],
            "email": ["iexact"],
            "is_associated": ["exact"],
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return InteractiveUser.get_queryset(queryset, info)


class UserGQLType(DjangoObjectType):
    """
    This type provides an abstraction of the various user types, TechnicalUser and InteractiveUser. It corresponds
    to the core_User table added in the modular version. The TechnicalUser is for now not exposed here as it is not
    managed through this API.
    """
    class Meta:
        model = User
        filter_fields = {
            "id": ["exact"],
            "username": ["exact", "icontains"],
            **prefix_filterset("i_user__", InteractiveUserGQLType._meta.filter_fields),
        }
        interfaces = (graphene.relay.Node,)
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return User.get_queryset(queryset, info)


class PermissionOpenImisGQLType(graphene.ObjectType):
    perms_name = graphene.String()
    perms_value = graphene.Int()


class ModulePermissionGQLType(graphene.ObjectType):
    module_name = graphene.String()
    permissions = graphene.List(PermissionOpenImisGQLType)


class ModulePermissionsListGQLType(graphene.ObjectType):
    module_perms_list = graphene.List(ModulePermissionGQLType)
