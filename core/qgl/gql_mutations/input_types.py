import graphene
from core.schema import OpenIMISMutation


class DeleteInputType(OpenIMISMutation.Input):
    uuids = graphene.List(graphene.UUID)


class ReplaceInputType(OpenIMISMutation.Input):
    uuid = graphene.UUID(required=True)