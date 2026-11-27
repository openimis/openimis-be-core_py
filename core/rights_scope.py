"""Which rights an action on a model requires - declared once, on the model.

Round 1 gave every model one definition of *which rows* a user may see:
``Model.get_queryset(queryset, user)``, reached from GraphQL through
``ScopedQuerysetMixin`` and from REST/FHIR by the viewsets calling it directly. This is
the same arrangement for *which actions* a user may perform.

A model answers for its own rights::

    class Contract(HistoryModel):
        @classmethod
        def get_rights(cls, action):
            from contract.apps import ContractConfig
            return {
                "query": ContractConfig.gql_query_contract_perms,
                "create": ContractConfig.gql_mutation_create_contract_perms,
                "update": ContractConfig.gql_mutation_update_contract_perms,
                "delete": ContractConfig.gql_mutation_delete_contract_perms,
            }.get(action)

Read the config *inside* the method, never at import time: ``_perms`` keys are only
populated in ``AppConfig.ready()``, so a module-level snapshot captures the empty
placeholder - and an empty right list is granted to everyone by ``has_perms``. Being a
method is what makes this safe, and it is why FHIR can share it: one definition, read at
the moment of the check, whichever API is asking.

A sub-resource names the foreign key that owns it and inherits that object's rights::

    class ContractDetails(HistoryModel):
        contract = models.ForeignKey(Contract, ...)
        scope_parent = "contract"

Editing a line of a contract is editing that contract, so it takes the contract's right
rather than one of its own. The parent is declared rather than inferred because it
cannot be guessed: ``ContractDetails`` has three foreign keys (contract, insuree,
contribution_plan_bundle) and only one of them is the owner.

Actions are named ``query`` / ``create`` / ``update`` / ``delete`` - the vocabulary
django uses for model permissions - plus whatever business actions a model wants to add.
A model that returns None for an action simply has no rule for it, and the lookup
continues to its scope parent.
"""

import logging
import re

logger = logging.getLogger(__name__)

# A sub-resource of a sub-resource is fine; a cycle is not.
_MAX_PARENT_DEPTH = 5

# HTTP verb -> action, for the REST and FHIR layers. PUT and PATCH are both an update.
VERB_ACTIONS = {
    "GET": "query",
    "HEAD": "query",
    "OPTIONS": "query",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


def _model_label(model):
    return f"{model._meta.app_label}.{model._meta.model_name}"


def scope_parent_of(model):
    """The model named by this model's ``scope_parent``, or None."""
    field_name = getattr(model, "scope_parent", None)
    if not field_name:
        return None
    try:
        return model._meta.get_field(field_name).related_model
    except Exception:
        logger.error(
            "%s declares scope_parent=%r, which is not a relation on it",
            _model_label(model), field_name,
        )
        return None


def model_rights(model, action):
    """
    The right list for `action` on `model`, or None when nothing declares one.

    None is not "allowed": it means no rule exists and the caller must fail closed. An
    empty list is a declared-but-empty right, which ``has_perms`` treats as granted to
    everyone - honoured, because that is has_perms' contract, but warned about.
    """
    current, depth = model, 0
    while current is not None and depth <= _MAX_PARENT_DEPTH:
        getter = getattr(current, "get_rights", None)
        if callable(getter):
            try:
                rights = getter(action)
            except Exception:
                logger.exception(
                    "%s.get_rights(%r) raised - treating as undeclared",
                    _model_label(current), action,
                )
                rights = None
            if rights is not None:
                rights = list(rights)
                if not rights:
                    logger.warning(
                        "%s.get_rights(%r) is an empty right list - `has_perms` treats "
                        "that as granted to everyone",
                        _model_label(current), action,
                    )
                return rights
        current = scope_parent_of(current)
        depth += 1
    if depth > _MAX_PARENT_DEPTH:
        logger.error(
            "scope_parent chain from %s is too deep or circular", _model_label(model)
        )
    return None


def has_model_right(user, model, action):
    """Whether `user` may perform `action` on `model`. Fails closed when undeclared."""
    rights = model_rights(model, action)
    if rights is None:
        logger.error(
            "no right declared for %s.%s and no scope_parent provides one - denying",
            _model_label(model), action,
        )
        return False
    return user.has_perms(rights)


# --- client-supplied field paths ------------------------------------------------------
#
# Exports and the deduplication summary take column paths from the client (``a__b__c``)
# and hand them to ``.values()`` / ``.values_list()``. The root rows are scoped by the
# list resolver, but a path can follow any foreign key to any model: without a check,
# ``user_created__i_user__password`` exports password hashes (CVE-2026-82491,
# CVE-2026-82492). `field_path_refusal` is the one place that decides which paths are
# acceptable.
#
# Known limit: only the *model* right of each related model is checked. The row scope of
# the joined row (its ``get_queryset``) is not re-applied; only the root rows are scoped.

FIELD_PATH_INVALID = "invalid"
FIELD_PATH_SECRET = "secret"
FIELD_PATH_UNAUTHORIZED = "unauthorized"

_JSON_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class FieldPathRefused(ValueError):
    """A client-supplied field path that may not be used, whatever the caller's rights."""

    def __init__(self, path, reason):
        super().__init__(f"field path {path!r} refused ({reason})")
        self.path = path
        self.reason = reason


def _is_stored_key(field, rest):
    target = getattr(field, "target_field", None)
    return len(rest) == 1 and target is not None and rest[0] == target.name


def field_path_relations(model, path):
    """
    The related models a ``__``-separated `path` crosses from `model`, in order.

    Raises `FieldPathRefused` when the path is unusable whatever the rights:

    * a segment that looks like a secret (`core.mutation_log_secrets.is_secret_key`);
    * an unknown field, a reverse or many-to-many relation (they multiply rows and reach
      sets of objects), or anything after a concrete field (lookups and transforms);
    * a key under a JSON field that is not a plain identifier.

    A foreign key as the last segment, or followed only by the field it points to
    (``group__id``), is the value stored on the row itself and crosses nothing.
    """
    from django.core.exceptions import FieldDoesNotExist
    from django.db.models import JSONField
    from core.mutation_log_secrets import is_secret_key

    segments = path.split("__") if isinstance(path, str) else []
    if not segments or any(not segment for segment in segments):
        raise FieldPathRefused(path, FIELD_PATH_INVALID)

    crossed = []
    current = model
    for index, segment in enumerate(segments):
        if is_secret_key(segment):
            raise FieldPathRefused(path, FIELD_PATH_SECRET)
        try:
            field = current._meta.get_field(segment)
        except FieldDoesNotExist:
            raise FieldPathRefused(path, FIELD_PATH_INVALID)
        is_last = index == len(segments) - 1

        if field.is_relation:
            if not (field.concrete and (field.many_to_one or field.one_to_one)):
                raise FieldPathRefused(path, FIELD_PATH_INVALID)
            if is_last or _is_stored_key(field, segments[index + 1:]):
                # The value the foreign key stores on this row: nothing is joined.
                return crossed
            current = field.related_model
            crossed.append(current)
            continue

        if isinstance(field, JSONField):
            for key in segments[index + 1:]:
                if is_secret_key(key):
                    raise FieldPathRefused(path, FIELD_PATH_SECRET)
                if not _JSON_KEY.match(key):
                    raise FieldPathRefused(path, FIELD_PATH_INVALID)
            return crossed

        if not is_last:
            raise FieldPathRefused(path, FIELD_PATH_INVALID)
    return crossed


def field_path_refusal(user, model, path):
    """
    Why `user` may not read `path` from rows of `model`, or None when it may.

    `FIELD_PATH_INVALID` / `FIELD_PATH_SECRET`: see `field_path_relations`.
    `FIELD_PATH_UNAUTHORIZED`: a crossed relation leads to a model whose ``query`` right
    the user does not hold, or which declares none (`has_model_right` fails closed).
    The root model itself is not checked: its rows are scoped by the caller.
    """
    try:
        crossed = field_path_relations(model, path)
    except FieldPathRefused as refused:
        return refused.reason
    for related_model in crossed:
        if not has_model_right(user, related_model, "query"):
            return FIELD_PATH_UNAUTHORIZED
    return None


def authorized_field_path(user, model, path):
    """Whether `user` may read the ``__``-separated `path` from rows of `model`."""
    return field_path_refusal(user, model, path) is None


def authorized_field_paths(user, model, paths):
    """
    The `paths` `user` may read from rows of `model`, in request order.

    Each refused path is dropped and logged. When paths were requested and none is
    left, PermissionError: a caller passing an empty list to ``values_list()`` would get
    every column of the model instead.
    """
    allowed = []
    for path in paths:
        refusal = field_path_refusal(user, model, path)
        if refusal is None:
            allowed.append(path)
        else:
            logger.warning(
                "%s: field path %r refused (%s) for user %s",
                _model_label(model), path, refusal, getattr(user, "id", None),
            )
    if paths and not allowed:
        raise PermissionError("None of the requested columns may be read")
    return allowed
