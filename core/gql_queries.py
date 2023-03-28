import graphene
import location.gql_queries
from core import ExtendedConnection, filter_validity
from core.models import Officer, Role, RoleRight, UserRole, User, InteractiveUser, UserMutation, Language
from graphene_django import DjangoObjectType
from location.models import HealthFacility
from .apps import CoreConfig
from django.utils.translation import gettext as _
from django.core.exceptions import PermissionDenied

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
            "dob": ["exact"],
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        queryset = queryset.filter(*filter_validity())
        return queryset


class RoleGQLType(DjangoObjectType):
    system_role_id = graphene.Int()

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


class UserRoleGQLType(DjangoObjectType):
    class Meta:
        model = UserRole
        filter_fields = {
            "id": ["exact"],
            "user": ["exact"],
            "role": ["exact"],
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
    language_id = graphene.String()
    health_facility = graphene.Field(
        location.gql_queries.HealthFacilityGQLType,
        description="Health Facility is not a foreign key in the database, this field resolves it manually, use only "
                    "if necessary.")
    roles = graphene.List(RoleGQLType, description="Same as userRoles but a straight list, without the M-N relation")

    class Meta:
        model = InteractiveUser
        interfaces = (graphene.relay.Node,)
        exclude = ("stored_password", "password", "private_key")
        filter_fields = {
            "id": ["exact"],
            "uuid": ["exact"],
            "last_name": ["icontains"],
            "other_names": ["icontains"],
            "phone": ["iexact"],
            "login_name": ["iexact"],
            "email": ["iexact"],
            "is_associated": ["exact"],
            "language_id": ["exact"],
        }
        connection_class = ExtendedConnection

    def resolve_health_facility(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_users_perms):
            raise PermissionDenied(_("unauthorized"))
        if self.health_facility_id:
            return HealthFacility.get_queryset(None, info).filter(pk=self.health_facility_id).first()
        else:
            return None

    def resolve_roles(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            raise PermissionDenied(_("unauthorized"))
        if self.user_roles:
            return Role.objects\
                .filter(validity_to__isnull=True)\
                .filter(user_roles__user_id=self.id, user_roles__validity_to__isnull=True)
        else:
            return None

    def resolve_userdistrict_set(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            raise PermissionDenied(_("unauthorized"))
        if self.userdistrict_set:
            return self.userdistrict_set.filter(*filter_validity())
        else:
            return None

    @classmethod
    def get_queryset(cls, queryset, info):
        return InteractiveUser.get_queryset(queryset, info)


class UserGQLType(DjangoObjectType):
    """
    This type provides an abstraction of the various user types, TechnicalUser and InteractiveUser. It corresponds
    to the core_User table added in the modular version. The TechnicalUser is for now not exposed here as it is not
    managed through this API.
    """
    client_mutation_id = graphene.String()
    rights = graphene.List(graphene.String)
    health_facility = graphene.Field(location.gql_queries.HealthFacilityGQLType)
    other_names = graphene.String()
    last_name = graphene.String()
    email = graphene.String()
    phone = graphene.String()

    class Meta:
        model = User
        filter_fields = {
            "id": ["exact"],
            "username": ["exact", "icontains"],
            **prefix_filterset("i_user__", InteractiveUserGQLType._meta.filter_fields),
            **prefix_filterset("officer__", OfficerGQLType._meta.filter_fields),
        }
        interfaces = (graphene.relay.Node,)
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        return User.get_queryset(queryset, info)

    def resolve_client_mutation_id(self, info):
        if not info.context.user.has_perms(CoreConfig.gql_query_users_perms):
            raise PermissionDenied(_("unauthorized"))
        user_mutation = self.mutations.select_related('mutation').filter(mutation__status=0).first()
        return user_mutation.mutation.client_mutation_id if user_mutation else None


class PermissionOpenImisGQLType(graphene.ObjectType):
    perms_name = graphene.String()
    perms_value = graphene.Int()


class ModulePermissionGQLType(graphene.ObjectType):
    module_name = graphene.String()
    permissions = graphene.List(PermissionOpenImisGQLType)


class ModulePermissionsListGQLType(graphene.ObjectType):
    module_perms_list = graphene.List(ModulePermissionGQLType)


class UserMutationGQLType(DjangoObjectType):
    """
    This intermediate object links Mutations to Users. Beware of the confusion between the user performing the mutation
    and the users affected by that mutation, the latter being listed in this object.
    """
    class Meta:
        model = UserMutation


class LanguageGQLType(DjangoObjectType):
    class Meta:
        model = Language
        filter_fields = {
            "language_code": ["exact"],
            "name": ["exact"],
            "sort_order": ["exact"]
        }

    @classmethod
    def get_queryset(cls, queryset, info):
        return queryset


class ValidationMessageGQLType(graphene.ObjectType):
    """
    This object is used for validation of user's input in forms (e.g. insuree code).
    """
    is_valid = graphene.Boolean()
    error_code = graphene.Int()
    error_message = graphene.String()

