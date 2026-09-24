import logging

logger = logging.getLogger(__name__)


class RightsDeclaration:
    """A module's rights, and what is derived from them."""

    def __init__(self, module_name, django_perms, perm_cfg):
        self.module_name = module_name
        self.django_perms = django_perms
        self.perm_cfg = dict(perm_cfg)

        declared = {
            (entity, action)
            for entity, actions in django_perms.items()
            for action in actions
        }
        unknown = sorted(set(self.perm_cfg.values()) - declared)
        if unknown:
            # At import time: a config key pointing at a non-existent action would
            # yield [], and `has_perms([])` returns True - so it would grant the
            # action to everybody instead of refusing it.
            raise KeyError(
                f"{module_name}: config keys pointing at an undeclared action: {unknown}"
            )
        self._key_by_action = {
            entity_action: key for key, entity_action in self.perm_cfg.items()
        }

    # --- declaration ------------------------------------------------------
    def _entries(self, entity, actions):
        try:
            entity_perms = self.django_perms[entity]
        except KeyError:
            raise KeyError(f"{self.module_name}: no permission declared for '{entity}'")
        missing = [action for action in actions if action not in entity_perms]
        if missing:
            raise KeyError(f"{self.module_name}: no permission for {entity}.{missing}")
        return [entity_perms[action] for action in actions]

    def perms(self, entity, *actions):
        """
        The openIMIS rights of these actions, in the shape the ``_perms`` config
        and ``has_perms`` expect: a list of decimal strings.

        This is the **declared default** value. A check must read ``configured``.
        A multi-action call means "one or the other": ``has_perms`` does an OR.
        """
        return [str(right_id) for _, right_id in self._entries(entity, actions)]

    def django_perm_names(self, entity, *actions):
        """
        The django permission names of these actions. Declared but **not**
        enforced: nothing grants them, so checking one would refuse every
        non-superuser.
        """
        return [name for name, _ in self._entries(entity, actions)]

    def default_cfg(self):
        """The ``_perms`` entries to inject into the module's ``DEFAULT_CFG``."""
        return {
            key: self.perms(*entity_action)
            for key, entity_action in self.perm_cfg.items()
        }

    # --- read at runtime --------------------------------------------------
    def configured(self, entity, action):
        """
        The **configured** value of the right - the one ``ModuleConfiguration``
        may have overridden - and not the declared default ``perms`` returns.

        The read happens at call time, not at import time: the ``_perms`` keys are
        only populated in ``AppConfig.ready()``, so a snapshot taken at import
        would capture the empty placeholder, which ``has_perms`` grants to
        everybody.

        Returns None when the action is not declared, so that the caller fails
        closed.
        """
        key = self._key_by_action.get((entity, action))
        if key is None:
            return None
        from django.apps import apps as django_apps

        # Through the registry rather than by importing the config class: that
        # class is defined after DEFAULT_CFG in apps.py, and resolving it here
        # saves having to care about that order.
        value = getattr(django_apps.get_app_config(self.module_name), key, None)
        if value is not None and not value:
            logger.warning(
                "%s: %s holds an empty list - `has_perms` treats that as granted "
                "to everybody. Check the ModuleConfiguration override.",
                self.module_name, key,
            )
        return value

    def require(self, user, entity, *actions, match="any"):
        """
        Whether `user` holds the rights of these actions - the "call site" form
        of ``configured``.

        ``match="any"`` (the default, like ``has_perms``) passes on any one of the
        actions; ``match="all"`` requires them all. Saves chaining ``has_perms``
        calls.
        """
        if match not in ("any", "all"):
            raise ValueError("match must be 'any' or 'all'")
        rights = []
        for action in actions:
            value = self.configured(entity, action)
            if value is None:
                raise KeyError(f"{self.module_name}: no permission for {entity}.{action}")
            rights.extend(value)
        return user.has_perms(rights, list_evaluation_or=(match == "any"))
