import graphene


class HistoryTypeEnum(graphene.Enum):
    """django-simple-history's ``history_type``: created, changed or deleted.

    graphene-django names enum values after the choice values, which turns
    ``+``, ``~`` and ``-`` into ``_``, ``__1`` and ``__2``. graphql-core 3
    rejects names starting with ``__`` (reserved for introspection), so the
    historical types declare this enum for the field instead.
    """

    class Meta:
        name = "HistoryType"

    CREATED = "+"
    CHANGED = "~"
    DELETED = "-"
