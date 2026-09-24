"""The deployment's answer to who must use a second factor.

Internal to core.auth.login.mfa_required, which is the one function that decides
whether a login needs a factor: it asks devices.has_second_factor first -
enrolment binds, whatever this says - and then asks here. Nothing else may ask
here directly, or the decision has two homes and a deployment that delegates it
to an identity provider has two things to change.

The policy is module configuration rather than a Django setting: the role names
it lists are rows in the same database, and the configuration model is where a
saved value can be validated against them and re-applied without a restart.
"""

import logging
from datetime import datetime

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db.models import Q

from core.apps import CoreConfig
from core.bootstrap import database_expected, unavailability_reason

logger = logging.getLogger(__name__)

#: Only the enrolled are bound.
OPTIONAL = "optional"
#: The roles named in second_factor_mandatory_roles, and the accounts every
#: right check exempts anyway.
PER_ROLE = "per_role"
#: Every interactive user.
MANDATORY = "mandatory"
POLICIES = (OPTIONAL, PER_ROLE, MANDATORY)


def configure(cfg):
    """Apply the two policy keys of a core configuration to CoreConfig.

    Called by load() with the effective configuration: at start, and again when
    the configuration row is saved, so a policy change takes effect without a
    restart.
    """
    CoreConfig.second_factor_policy = cfg["second_factor_policy"]
    CoreConfig.second_factor_mandatory_roles = list(
        cfg["second_factor_mandatory_roles"] or []
    )
    logger.info(
        "Second-factor policy: %s%s",
        CoreConfig.second_factor_policy,
        (
            " (roles: %s)" % ", ".join(CoreConfig.second_factor_mandatory_roles)
            if CoreConfig.second_factor_policy == PER_ROLE
            else ""
        ),
    )


def _read():
    """The policy the core configuration row holds, straight from the database.

    Not ModuleConfiguration.get_or_default: that tolerates every error and
    answers with the defaults, which here would turn an unreadable row into
    "optional" - everyone exempt.
    """
    from core.apps import DEFAULT_CFG, MODULE_NAME
    from core.models import ModuleConfiguration

    row = ModuleConfiguration.objects.filter(
        Q(is_disabled_until=None) | Q(is_disabled_until__lt=datetime.now()),
        layer="be",
        module=MODULE_NAME,
    ).first()
    return {**DEFAULT_CFG, **(row._cfg if row else {})}


#: The last read failed, as opposed to the row holding no valid policy: only
#: the first leaves the policy unknown and waiting for the next read.
_unread = False


def is_unread():
    return _unread


def load():
    """Read the policy from the configuration row and apply it.

    Called from CoreConfig.ready() and after a configuration row is saved. A
    read that fails leaves the policy unknown rather than defaulting it, and
    mandates() tries again at the next login.
    """
    global _unread
    if not database_expected():
        logger.info("Second-factor policy not loaded: %s", unavailability_reason())
        _unread = True
        CoreConfig.second_factor_policy = None
        return
    try:
        cfg = _read()
    except Exception:
        # The traceback once: every login retries this while the row stays
        # unreadable.
        logger.warning(
            "Second-factor policy could not be read; logins of users without a "
            "device are refused until it can be",
            exc_info=not _unread,
        )
        _unread = True
        CoreConfig.second_factor_policy = None
        return
    _unread = False
    configure(cfg)


def _is_privileged(user):
    """Power that comes from a flag rather than a role, so it cannot be listed.

    Three signals, asked separately on purpose:

    - is_superuser, the column on core_User: what has_role_perms short-circuits
      on before it looks at any right.
    - is_imis_admin: that flag, or the IMIS Administrator role. Asked as well as
      is_superuser rather than instead of it - InteractiveUser.is_imis_admin is
      marked deprecated and due for removal, and a predicate that reached
      superusers only through it would fail open the day it goes.
    - is_staff: what the admin site gates on. For an interactive user it is
      is_superuser again; for a technical user it is the TechnicalUser column,
      and it is the only signal that catches an admin-capable technical account.

    Deliberately not asked: TechnicalUser.is_superuser. core_User carries its
    own is_superuser column and nothing syncs the two, so the technical row's
    flag escalates nothing, and refusing an integration over it would be a
    break for nothing. Where it does matter it shows up as is_staff, which the
    admin form sets from it.
    """
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or user.is_imis_admin
    )


def mandates(user):
    """Whether the deployment binds `user` to a second factor, enrolled or not.

    One account is outside every policy: a technical user that is not
    privileged. That is a pure integration account - no admin, no rights of its
    own, nothing but the API - and refusing it would break the integrations
    HTTP Basic stays enabled for. A technical user that is privileged is not
    exempt: it reaches the Django admin like any administrator.
    """
    if user.i_user is None and not _is_privileged(user):
        # Outside every policy, so there is nothing to decide - not even while
        # the policy cannot be read.
        return False
    if CoreConfig.second_factor_policy is None:
        load()
        if is_unread():
            raise ImproperlyConfigured(
                "The second-factor policy could not be read; refusing to decide "
                "who needs a second factor until it can be."
            )
    mode = CoreConfig.second_factor_policy
    if mode not in POLICIES:
        # A typo in the configuration must not quietly become "optional"
        # (everyone exempt) or "mandatory" (everyone locked out). A startup
        # check reports the same thing; this is for a server that skipped it.
        raise ImproperlyConfigured(
            f"second_factor_policy is {mode!r}; it must be one of "
            f"{', '.join(POLICIES)}."
        )
    if mode == OPTIONAL:
        return False
    if user.i_user is None:
        return _is_privileged(user)
    if mode == MANDATORY:
        return True
    if _is_privileged(user):
        # The accounts has_role_perms never checks. A per-role mandate that
        # exempted the accounts every right check exempts would bind everyone
        # except the ones it is for.
        return True
    # Imported here: core.apps must stay importable before the app registry is
    # ready, and this module is imported from it.
    from core.models import Role, UserRole

    return Role.objects.filter(
        *Role.filter_validity(),
        *UserRole.filter_validity(prefix="user_roles__"),
        user_roles__user=user.i_user,
        name__in=CoreConfig.second_factor_mandatory_roles,
    ).exists()


def validate_configuration(instance):
    """Refuse a core configuration row this module could not act on.

    Registered for the core module; ModuleConfiguration.clean() calls it on
    every save. Missing keys are fine - the row is merged over the defaults -
    so only what the row itself says is checked. A role name matching no valid
    role is refused here, at save time: at login it would match nobody, and
    everyone holding the intended role would be silently exempt.
    """
    cfg = instance._cfg
    if not isinstance(cfg, dict):
        # clean() guards the JSON syntax but not its shape, so a valid-JSON
        # list arrives here intact and would raise AttributeError out of
        # save(). The model's contract is a field error.
        raise ValidationError({"config": "The configuration must be a JSON object."})
    mode = cfg.get("second_factor_policy", OPTIONAL)
    if mode not in POLICIES:
        raise ValidationError(
            {
                "config": "second_factor_policy must be one of "
                f"{', '.join(POLICIES)}, not {mode!r}."
            }
        )
    roles = cfg.get("second_factor_mandatory_roles", []) or []
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise ValidationError(
            {"config": "second_factor_mandatory_roles must be a list of role names."}
        )
    if roles:
        from core.models import Role

        known = set(
            Role.objects.filter(*Role.filter_validity(), name__in=roles).values_list(
                "name", flat=True
            )
        )
        unknown = sorted(set(roles) - known)
        if unknown:
            raise ValidationError(
                {
                    "config": "second_factor_mandatory_roles names no existing role: "
                    + ", ".join(unknown)
                }
            )


def reload_configuration(instance):
    """Re-apply the effective core configuration after a row is committed.

    Reads it the way CoreConfig.ready() does rather than trusting the saved
    instance: a row disabled with is_disabled_until, or a second row, resolves
    exactly as it will at the next start.
    """
    load()
