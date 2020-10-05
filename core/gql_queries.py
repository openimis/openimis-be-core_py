import graphene
from core import ExtendedConnection, filter_validity
from graphene_django import DjangoObjectType

from core.models import Officer

class OfficerGQLType(DjangoObjectType):
    class Meta:
        model = Officer
        interfaces = (graphene.relay.Node,)
        filter_fields = {
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
