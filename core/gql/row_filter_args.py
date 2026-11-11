"""OP-3317 phase 2: the GraphQL arguments a connection already takes, mapped
onto the OP-2029 ``validity`` / ``audits`` contract of ``Model.get_queryset``.

    showHistory: true          -> audits=ALL
    isDeleted: true            -> validity=DELETED_NOW
    isDeleted: null (explicit) -> validity=ALL   (unreachable from GraphQL with graphql-core 2:
                                                  no null literal, and a null variable reaches
                                                  the resolver as an absent argument)
    dateValidFrom__Gte / dateValidTo__Lte
                               -> validity=between(from, to)  (business-validity models only)

A caller passing none of them gets the model's own default, so nothing changes
for the queries that do not ask (phase 1 rule).

A connection opts in to these arguments with ``**row_filter_arguments()``. Its
resolver no longer filters validity itself: it maps the arguments the frontend
already sends (``showHistory``, a ``uuid`` lookup, ...) onto validity / audits
with ``legacy_row_filters``. Those are defaults: an explicit ``isDeleted`` /
``showHistory`` overrides them, so the new arguments are available without any
frontend change being required.

The connection field stores the mapping on the request for the time graphene
calls ``DjangoObjectType.get_queryset(queryset, info)`` -- which receives no
arguments (graphene_django/fields.py) -- and ``ScopedQuerysetMixin`` hands it
to the model.
"""
import inspect
from contextlib import contextmanager

from core.models.row_filters import Audits, Validity

_CONTEXT_ATTR = "_openimis_row_filters"
_LEGACY_ATTR = "_openimis_legacy_row_filters"


def row_filter_arguments():
    """The connection arguments mapped onto validity / audits, to splat into a field."""
    import graphene

    return {
        "show_history": graphene.Boolean(
            description="Include the audit (history) copies of the rows."),
        "is_deleted": graphene.Boolean(
            description="true: deleted rows only; false: live rows only; null: both."),
    }


def legacy_row_filters(info, args, validity=None, audits=None):
    """Called by a resolver: what its legacy arguments mean as validity / audits.

    graphene runs the resolver before the connection's resolve_queryset, which is
    where row_filters_in_context reads these back as defaults under the explicit
    arguments. The resolver must not filter validity itself any more.

    Returns the effective ``{'validity', 'audits'}`` (explicit ``args`` over the
    defaults), for a resolver that needs the same rows before graphene applies
    them -- an existence check, say.
    """
    rows = {}
    if validity is not None:
        rows["validity"] = validity
    if audits is not None:
        rows["audits"] = audits
    context = getattr(info, "context", None)
    if context is not None:
        setattr(context, _LEGACY_ATTR, rows)
    explicit = row_filters_from_args(args)
    return {k: v for k, v in {**rows, **explicit}.items() if k in ("validity", "audits")}


def _arg(args, *names):
    for name in names:
        if name in args:
            return True, args[name]
    return False, None


def row_filters_from_args(args):
    """{'validity': ..., 'audits': ..., 'validity_range': (from, to)} from connection args."""
    rows = {}
    present, show_history = _arg(args, "showHistory", "show_history")
    if present and show_history:
        rows["audits"] = Audits.ALL
    present, is_deleted = _arg(args, "isDeleted", "is_deleted")
    if present:
        rows["validity"] = Validity.DELETED_NOW if is_deleted else (
            Validity.ALL if is_deleted is None else Validity.NOW)
    _, valid_from = _arg(args, "dateValidFrom__Gte", "date_valid_from__gte")
    _, valid_to = _arg(args, "dateValidTo__Lte", "date_valid_to__lte")
    if valid_from is not None or valid_to is not None:
        rows["validity_range"] = (valid_from, valid_to)
    return rows


@contextmanager
def row_filters_in_context(info, args):
    context = getattr(info, "context", None)
    if context is None:
        yield
        return
    previous = getattr(context, _CONTEXT_ATTR, None)
    # one connection's legacy defaults must not leak into the next field of the request
    legacy = getattr(context, _LEGACY_ATTR, None) or {}
    if hasattr(context, _LEGACY_ATTR):
        delattr(context, _LEGACY_ATTR)
    setattr(context, _CONTEXT_ATTR, {**legacy, **row_filters_from_args(args)})
    try:
        yield
    finally:
        setattr(context, _CONTEXT_ATTR, previous)


def row_filter_kwargs(model, info):
    """The validity/audits kwargs to pass to ``model.get_queryset`` for this request."""
    rows = getattr(getattr(info, "context", None), _CONTEXT_ATTR, None) or {}
    kwargs = {k: rows[k] for k in ("validity", "audits") if k in rows}
    valid_range = rows.get("validity_range")
    if valid_range and "validity" not in kwargs:
        get_fields = getattr(model, "get_business_validity_fields", None)
        if callable(get_fields) and get_fields():
            kwargs["validity"] = Validity.between(*valid_range)
    return kwargs


_ACCEPTS = {}


def accepts_row_filters(get_queryset):
    """True when a get_queryset takes validity/audits (OP-2029) or **kwargs."""
    key = getattr(get_queryset, "__func__", get_queryset)
    if key not in _ACCEPTS:
        try:
            params = inspect.signature(get_queryset).parameters.values()
        except (TypeError, ValueError):
            _ACCEPTS[key] = False
        else:
            _ACCEPTS[key] = any(
                p.kind == p.VAR_KEYWORD or p.name in ("validity", "audits") for p in params)
    return _ACCEPTS[key]
