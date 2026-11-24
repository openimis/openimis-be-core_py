import graphene
from django.test import SimpleTestCase
from graphene_django import DjangoObjectType
from graphene_django.registry import Registry

from core.models import InteractiveUser, User


# A registry of its own: the global one would hand these types to the real schema.
_registry = Registry()


class _InteractiveUserType(DjangoObjectType):
    class Meta:
        model = InteractiveUser
        fields = ("id", "login_name")
        registry = _registry

    @classmethod
    def get_queryset(cls, queryset, info):
        # Row security that hides every row: lists and lookups see nothing.
        return queryset.none()


class _UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = ("id", "username", "i_user")
        registry = _registry


class _Query(graphene.ObjectType):
    user = graphene.Field(_UserType)

    def resolve_user(self, info):
        user = User(id="00000000-0000-0000-0000-000000000001", username="u1")
        user.i_user = InteractiveUser(id=7, login_name="u1")
        return user


class ForeignKeyTraversalTest(SimpleTestCase):
    # graphene-django 3 resolves a foreign key through the target type's
    # get_queryset (get_node) and answers null when it hides the row; graphene-django 2
    # returned the related object. openIMIS keeps the graphene-django 2 behaviour:
    # changing what a user sees through a relation is not a dependency bump's call.

    def test_foreign_key_returns_the_related_object(self):
        result = graphene.Schema(query=_Query).execute("{ user { username iUser { loginName } } }")
        self.assertIsNone(result.errors)
        self.assertEqual(result.data["user"]["iUser"], {"loginName": "u1"})
