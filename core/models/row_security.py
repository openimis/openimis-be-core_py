"""Row security, declared once per model and reused by every API.

The restriction on *which rows a user may see* belongs to the model, not to any
one API surface. GraphQL, REST and FHIR all ask the same model the same
question, so there is one implementation to audit and no surface can quietly
skip it -- which is what happens when the filter is written on a
``DjangoObjectType`` instead: graphene calls it, REST and FHIR never do.

In openIMIS this is, in the main, *location* security: a row is visible when the
location it hangs off sits inside the districts the user is assigned to.

Two API styles, one implementation
----------------------------------

``filter_location`` is the explicit one, shaped like ``filter_validity`` -- a
list of ``Q`` objects, splatted into ``filter()``, with a ``prefix`` naming the
path from the queryset being filtered to the model that owns the location::

    # in a claim item resolver or service
    queryset = queryset.filter(*Claim.filter_location(user, prefix="claim__"))

Called on the model that *owns* the location, with the prefix that reaches it.
The model knows its own paths; the caller only states how to get there.

``row_scope`` is the declarative one, for models whose rule is nothing more than
"same as my parent" or "this location path". Leave it unset for a model with no
row security::

    class ClaimItem(...):
        row_scope = ParentScope("claim")

Both end up in ``filter_location``. A scope is declared on the model it belongs
to -- there is no central table of which model is scoped how, because that would
put every module's business rules in core.

Why a child composes rather than restates
-----------------------------------------

A child is exactly as restricted as its parent. A claim item is visible when its
claim is; an insuree photo when its insuree is. So the rule belongs once, on the
root that owns the location, and a child composes onto it by prefixing its own
foreign key -- ``ParentScope("claim")`` turns Claim's
``health_facility__location`` into ``claim__health_facility__location``, and a
second hop turns it into ``claim_service__claim__health_facility__location``.
Restating the path in the child is how the two drift apart.

The most specific parent wins: a policy is scoped through its head insuree, not
through its product. The product says which benefits apply; the insuree says
whose data this is.

A model may reach a location by more than one route, and the routes are OR'ed:
an insuree carries ``current_village``, but may not, in which case the family's
location answers instead. A fallback here is another path, not a special case.
"""

import logging

from django.core.cache import cache
from django.db import DatabaseError
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)

DEFAULT_LOC_TYPES = ("D",)


def resolve_location_filter():
    """The location module's filter, or None when it is not installed.

    Imported lazily because core sits below location in the dependency order.
    This is the same lazy import the module code already does today (see
    Insuree.get_queryset), kept in one place instead of repeated per model.

    A model declares *which path* reaches its location; location turns a path
    into a filter. Neither side needs a registry of the other's models for
    that, so there isn't one: a scope is declared on the model it belongs to.
    """
    try:
        from location.models import LocationManager
    except ImportError:
        return None

    def build_filter(user, prefix, loc_types):
        return LocationManager().build_user_location_filter_query(
            user, prefix=prefix, loc_types=list(loc_types)
        )

    return build_filter


class RowSecurityMixin:
    """Gives every model `filter_location`, `location_paths` and `get_queryset`."""

    #: Declarative row security: a LocationScope or ParentScope. None means
    #: no row security -- which is the case for most models, so it is the
    #: default. Override get_queryset directly when the rule needs logic a
    #: Scope cannot express.
    row_scope = None

    @staticmethod
    def scoping_user(context):
        """Normalise a graphene ``ResolveInfo``, a user, or None into a user.

        Duck-typed on ``.context`` rather than importing graphql, so models stay
        free of a GraphQL dependency. Callers on the GraphQL path have
        historically passed ``info``; several models carry their own
        ``isinstance(user, ResolveInfo)`` check because of it. Pass either.
        """
        if context is None:
            return None
        request = getattr(context, "context", None)
        if request is not None:
            return getattr(request, "user", None)
        return context

    @classmethod
    def location_paths(cls):
        """Paths from this model to a Location, to be OR'ed.

        Empty means this model declares no location scope.
        """
        if cls.row_scope is None:
            return ()
        return tuple(cls.row_scope.location_paths(cls))

    @classmethod
    def filter_location(
        cls, user, prefix="", paths=None, loc_types=None, link_types=None
    ):
        """``Q`` objects narrowing rows to the locations ``user`` may see.

        Shaped like ``filter_validity``, and used the same way::

            queryset.filter(*Claim.filter_location(user, prefix="claim__"))

        ``prefix`` is the path from the queryset being filtered to *this* model,
        including the trailing ``__``. ``paths`` overrides this model's declared
        paths for a one-off call. Returns ``[]`` -- which splats to nothing --
        when there is no location scope to apply, so the call is always safe to
        write.

        ``link_types`` names the credential that governs these rows (claim ->
        CLAIM_ADMIN, insuree -> ENROLMENT). It is carried now and honoured once
        UBA ships; a credential must not narrow a scope it says nothing about,
        so it is per-call and never a global default.
        """
        paths = tuple(paths) if paths else cls.location_paths()
        if not paths:
            return []

        build_filter = resolve_location_filter()
        if build_filter is None:
            # A misconfiguration, not a request: without the location module
            # there are no districts to filter by. Loud, so it is not missed.
            logger.error(
                "%s asks for a location filter but none is available; "
                "returning no restriction",
                cls.__name__,
            )
            return []

        if loc_types is None:
            loc_types = getattr(cls.row_scope, "loc_types", None) or DEFAULT_LOC_TYPES
        if link_types is None:
            link_types = getattr(cls.row_scope, "link_types", None)

        user = cls.scoping_user(user)
        if user is None or getattr(user, "is_anonymous", True):
            # LocationManager fails *open* for anyone who is not an
            # InteractiveUser: it logs "Access without filter" and returns every
            # row. Every hand-written get_queryset in the modules carries its
            # own `if user.is_anonymous: return nothing` guard for exactly this
            # reason, so the wrapper owns it rather than inheriting the hole.
            return [Q(pk__in=[])]

        # From here the interactive user is what the location filter wants; it
        # handles a technical user (deliberately unfiltered) itself.
        scoping = getattr(user, "_u", user)

        condition = None
        for path in paths:
            term = build_filter(scoping, f"{prefix}{path}", loc_types)
            condition = term if condition is None else (condition | term)
        return [condition]

    @classmethod
    def get_queryset(cls, queryset, user=None):
        """The rows ``user`` may see.

        Applies ``row_scope`` when the model declares one. Unrestricted
        otherwise -- deliberately: most openIMIS models hold reference or
        configuration data with no row security, and a fail-closed default
        would make this mixin impossible to apply broadly. Whether a model is
        secured stays a decision in that model.

        A model needing logic a Scope cannot express overrides this directly;
        the models that already do keep working untouched.
        """
        if cls.row_scope is None:
            return queryset
        return cls.row_scope.filter(queryset, cls.scoping_user(user), cls)


class Scope:
    """How a model's rows narrow to the ones a user may see."""

    loc_types = DEFAULT_LOC_TYPES
    link_types = None

    def location_paths(self, model):
        """Paths from ``model`` to a Location, to be OR'ed."""
        raise NotImplementedError

    def filter(self, queryset, user, model):
        conditions = model.filter_location(
            user,
            paths=self.location_paths(model),
            loc_types=self.loc_types,
            link_types=self.link_types,
        )
        return queryset.filter(*conditions) if conditions else queryset


class LocationScope(Scope):
    """Narrow to the user's locations, reached by one or more paths.

    Paths are OR'ed, so a fallback is just a second path::

        row_scope = LocationScope(
            "current_village__parent__parent",
            "family__location__parent__parent",
        )
    """

    def __init__(self, *paths, loc_types=DEFAULT_LOC_TYPES, link_types=None):
        if not paths:
            raise ValueError("LocationScope needs at least one path")
        self.paths = tuple(paths)
        self.loc_types = tuple(loc_types)
        self.link_types = link_types

    def location_paths(self, model):
        return self.paths


class ParentScope(Scope):
    """Inherit the parent's scope, applied through ``field``.

    The parent's paths are prefixed with this model's foreign key, so the rule
    stays declared once on whichever ancestor owns the location.

    ``allow_null`` is for a nullable parent: a row that has no parent at all has
    nothing to narrow it by, so it stays visible -- the same way a null location
    does in ``build_user_location_filter_query`` and a null subject does in
    ``GenericScope``. It is opt-in because the alternative reading ("no parent,
    no reason to show it") is the safer default, and only the model knows which
    of the two its nullable foreign key means. It matters only on the subquery
    path below; when the parent's paths compose, a null parent already falls
    through the outer join onto the location filter's own ``isnull`` term.
    """

    def __init__(self, field, loc_types=None, link_types=None, allow_null=False):
        self.field = field
        self._loc_types = loc_types
        self._link_types = link_types
        self.allow_null = allow_null

    def _parent_scope(self, model):
        parent = model._meta.get_field(self.field).related_model
        return parent, getattr(parent, "row_scope", None)

    def _inherited(self, model, attribute, own):
        if own is not None:
            return own
        _parent, scope = self._parent_scope(model)
        return getattr(scope, attribute, None)

    def location_paths(self, model):
        """The parent's paths, prefixed. Empty when the parent has no paths.

        A parent with a hand-written ``get_queryset`` exposes no paths to
        compose; ``filter`` falls back to a subquery for that case.
        """
        parent, scope = self._parent_scope(model)
        if scope is None:
            return ()
        # Inherit granularity and credential along with the paths.
        self.loc_types = self._loc_types or getattr(
            scope, "loc_types", DEFAULT_LOC_TYPES
        )
        self.link_types = self._link_types or getattr(scope, "link_types", None)
        return tuple(f"{self.field}__{path}" for path in scope.location_paths(parent))

    def filter(self, queryset, user, model):
        """Narrow to rows whose parent the user may see.

        Prefers composing the parent's location paths into this queryset: one
        join, no subquery. When the parent scopes itself in code rather than
        declaratively -- which is how the ~37 already-secured models do it --
        there is no path to compose, so ask the parent for its queryset and
        restrict through it instead. Same answer, and it means a child can be
        secured today without its parent being migrated first.
        """
        paths = self.location_paths(model)
        if paths:
            return super().filter(queryset, user, model)

        parent, _scope = self._parent_scope(model)
        parent_get_queryset = getattr(parent, "get_queryset", None)
        if not callable(parent_get_queryset):
            logger.warning(
                "%s scopes through %s.%s, which has no row security at all",
                model.__name__,
                self.field,
                parent.__name__,
            )
            return queryset
        allowed = parent_get_queryset(parent.objects.all(), user)
        condition = Q(**{f"{self.field}__in": allowed})
        if self.allow_null:
            condition |= Q(**{f"{self.field}__isnull": True})
        return queryset.filter(condition)


def is_row_secured(model):
    """True when ``model`` narrows its own rows, declaratively or in code."""
    return (
        getattr(model, "row_scope", None) is not None
        or "get_queryset" in model.__dict__
    )


def _generic_fk_fields(model, name):
    """The (content type, id) column names behind a GenericForeignKey."""
    for field in model._meta.private_fields:
        if field.name == name and hasattr(field, "ct_field"):
            return field.ct_field, field.fk_field
    raise ValueError(f"{model.__name__} has no GenericForeignKey named {name!r}")


def present_content_type_ids(model, ct_field):
    """The content types this table actually holds, cached until a new one lands.

    A generic foreign key may point at any model, so scoping one by asking every
    installed model for its rows would build a subquery per model, nearly all of
    them matching nothing. Only the types actually stored matter, and that set
    changes about as often as a new kind of invoice subject is introduced -- so
    it is read once, cached without expiry, and dropped by a ``post_save`` that
    sees a type not in the cached set.

    Returns ``None`` when content types cannot be read at all: an empty
    ``django_content_type``, or tables that do not exist yet. Both mean "before
    migration", where the caller must skip filtering rather than fail.
    """
    from django.contrib.contenttypes.models import ContentType

    key = f"row_security:generic_cts:{model._meta.label_lower}:{ct_field}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        if not ContentType.objects.exists():
            return None
        ids = sorted(
            ct_id
            for ct_id in model.objects.order_by()
            .values_list(f"{ct_field}_id", flat=True)
            .distinct()
            if ct_id is not None
        )
    except DatabaseError as exc:
        logger.debug("content types unavailable for %s: %s", model.__name__, exc)
        return None

    cache.set(key, ids, None)
    _invalidate_on_new_content_type(model, ct_field, key)
    return ids


def _invalidate_on_new_content_type(model, ct_field, key):
    """Drop the cached set when a row brings in a type it does not list."""

    def drop_if_new(sender, instance, **kwargs):
        known = cache.get(key)
        ct_id = getattr(instance, f"{ct_field}_id", None)
        if known is not None and ct_id is not None and ct_id not in known:
            cache.delete(key)

    post_save.connect(
        drop_if_new,
        sender=model,
        weak=False,
        dispatch_uid=f"row_security_content_types:{key}",
    )


class GenericScope(Scope):
    """Inherit the scope of whatever a generic foreign key points at.

    ``ParentScope`` cannot serve here: a generic foreign key is a content type
    plus a loose id, not an ORM path, so there is no join to compose and no
    single parent model to ask. The filter is instead one term per content type
    present in the table -- "this type, and an id its own row security allows" --
    OR'ed together::

        subject_type = Invoice AND subject_id IN (invoices the user may see)
        OR subject_type = Policy AND subject_id IN (policies the user may see)

    A type whose model has no row security contributes its rows unfiltered;
    there is nothing to narrow them by, and refusing them would hide data no
    rule says is restricted. Rows with no subject at all stay visible, the same
    way a null location does in ``build_user_location_filter_query``.

    The id column holds ``str(pk)``, so the *pk* is cast to text rather than the
    column to a uuid: every pk casts cleanly, and the comparison stays a
    subquery instead of dragging the ids through Python.
    """

    def __init__(self, field="subject"):
        self.field = field

    def location_paths(self, model):
        """None: a generic foreign key is not a path a child could compose."""
        return ()

    def filter(self, queryset, user, model):
        ct_field, fk_field = _generic_fk_fields(model, self.field)
        content_type_ids = present_content_type_ids(model, ct_field)
        if not content_type_ids:
            # No content types, or none stored yet: nothing to narrow.
            return queryset

        from django.contrib.contenttypes.models import ContentType

        condition = Q(**{f"{ct_field}__isnull": True})
        narrowed = False
        for ct_id in content_type_ids:
            subject = ContentType.objects.get_for_id(ct_id).model_class()
            if subject is None or not is_row_secured(subject):
                condition |= Q(**{ct_field: ct_id})
                continue
            allowed = subject.get_queryset(subject._default_manager.all(), user)
            allowed = allowed.annotate(
                _row_security_pk=Cast("pk", TextField())
            ).values("_row_security_pk")
            condition |= Q(**{ct_field: ct_id, f"{fk_field}__in": allowed})
            narrowed = True

        if not narrowed:
            # Every type present scopes nothing: the OR would match every row,
            # so leave the queryset alone rather than pay for the subqueries.
            return queryset
        return queryset.filter(condition)
