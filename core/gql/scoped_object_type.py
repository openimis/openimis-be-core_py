"""Wire a graphene type's queryset hook to its model's row security.

graphene-django calls ``DjangoObjectType.get_queryset(cls, queryset, info)``
from ``DjangoConnectionField.resolve_queryset`` (graphene_django/fields.py:131),
applying it to whatever the resolver returned. That makes it a convenient place
to filter -- and the wrong place to *define* the filter, because REST and FHIR
never call it.

So this mixin holds no policy. It normalises ``info`` to a user and hands the
queryset to ``Model.get_queryset``, which is the single definition every API
shares. Adding the mixin to a type is enough; there is nothing to keep in sync.

    class InsureeGQLType(ScopedQuerysetMixin, DjangoObjectType):
        class Meta:
            model = Insuree

For GraphQL-only shaping -- a ``.distinct()`` undoing a filter JOIN, say, which
is an artefact of the GraphQL query and not a security rule -- override
``refine_queryset``. Keeping that separate is the point: it stays visibly *not*
row security, so nobody later mistakes it for a restriction other APIs are
missing.
"""


class ScopedQuerysetMixin:
    """Delegates this type's queryset hook to the model's row security."""

    @classmethod
    def get_queryset(cls, queryset, info):
        model = getattr(getattr(cls, "_meta", None), "model", None)
        scope = getattr(model, "get_queryset", None)
        if callable(scope):
            # Hand the model a user, never a ResolveInfo: the model owns the
            # policy, not the knowledge of which API is asking.
            user = getattr(getattr(info, "context", None), "user", None)
            queryset = scope(queryset, user)
        return cls.refine_queryset(queryset, info)

    @classmethod
    def refine_queryset(cls, queryset, info):
        """GraphQL-only shaping applied after row security. Not a security hook."""
        return queryset
