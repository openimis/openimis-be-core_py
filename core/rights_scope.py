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
