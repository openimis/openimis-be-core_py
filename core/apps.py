import sys
import os
import importlib
import logging
from django.apps import AppConfig
from django.conf import settings

from core.bootstrap import (
    database_expected,
    optional_database,
    unavailability_reason,
)

logger = logging.getLogger(__name__)

MODULE_NAME = "core"

this = sys.modules[MODULE_NAME]

# Permissions, keyed by entity then action. Each action carries the pair
# `(django permission name, openIMIS numeric right)`.
#
# Two names for one action because `RoleRight.right_id` is an IntegerField and
# `InteractiveUser.rights_str` compares against `str(int)`: a right can only ever be
# the decimal string of an integer, so a django style name can never be stored on a
# role. The **integer is what is enforced today**; the django name is declared next to
# it, ready for the day permissions move to django's own tables.
#
# `query` / `create` / `update` / `delete` line up with the default model permissions
# django creates at post_migrate. Anything else (`duplicate`, `replace`, `profile`) is a
# business action and only becomes a grantable django row once the model declares it in
# `Meta.permissions` - none of the core models do yet, so those names are declaration
# only.
#
# All four models named here (User, Role, Officer, ClaimAdmin) live in the `core` app
# (`core/models/user.py`) with no `Meta.app_label` override, hence the `core.` prefix on
# every name. NB this differs per assembly: where ClaimAdmin has been moved into the
# claim module its name becomes `claim.view_claimadmin`.
DJANGO_PERMS = {
    "user": {
        "query": ("core.view_user", 121701),
        # The caller's own profile, not another user's record.
        "profile": ("core.view_user_profile", 122000),
        "create": ("core.add_user", 121702),
        "update": ("core.change_user", 121703),
        "delete": ("core.delete_user", 121704),
    },
    "role": {
        "query": ("core.view_role", 122001),
        "create": ("core.add_role", 122002),
        "update": ("core.change_role", 122003),
        "delete": ("core.delete_role", 122004),
        "duplicate": ("core.duplicate_role", 122005),
        "replace": ("core.replace_role", 122006),
    },
    # TODO consider moving the rights related to ClaimAdmin and EnrolmentOfficer into
    #  the modules related to that type of user, e.g. EnrolmentOfficer -> policy,
    #  ClaimAdmin -> claim.
    "enrolmentOfficer": {
        "query": ("core.view_officer", 121501),
        "create": ("core.add_officer", 121502),
        "update": ("core.change_officer", 121503),
        "delete": ("core.delete_officer", 121504),
    },
    "claimAdministrator": {
        "query": ("core.view_claimadmin", 121601),
        "create": ("core.add_claimadmin", 121602),
        "update": ("core.change_claimadmin", 121603),
        "delete": ("core.delete_claimadmin", 121604),
    },
    # Not a model: unmasking is a capability, so there is no django model permission to
    # line it up with. The name is a placeholder until it gets a home.
    "maskedData": {
        "query": ("core.view_masked_data", 900101),
    },
}


def _perm_entries(entity, actions):
    try:
        entity_perms = DJANGO_PERMS[entity]
    except KeyError:
        raise KeyError(f"No permissions declared for '{entity}'")
    missing = [action for action in actions if action not in entity_perms]
    if missing:
        raise KeyError(f"No permission declared for {entity}.{missing}")
    return [entity_perms[action] for action in actions]


def perms(entity, *actions):
    """
    The openIMIS rights of those actions, as the list of decimal strings the `_perms`
    config and `has_perms` expect. This is what is enforced today.

    A multi action call is an **any of** list: `has_perms` ORs by default
    (`core.access.has_role_perms`), so `perms("role", "update", "replace")` passes for a
    user holding either. Pass `list_evaluation_or=False` to `has_perms` for "all of".
    """
    return [str(right_id) for _, right_id in _perm_entries(entity, actions)]


def django_perms(entity, *actions):
    """
    The django permission names of those actions. Declared but **not** enforced yet:
    nothing grants them, so checking one today would deny every non superuser. Kept so
    that the move to django permissions is a config change rather than an API one.

    Mind the semantics flip: django's own `User.has_perms` requires **all** of the
    permissions it is given, where openIMIS `has_perms` defaults to any. Do not hand a
    multi action list to both and expect the same answer.
    """
    return [perm for perm, _ in _perm_entries(entity, actions)]


def require(user, entity, *actions, match="any"):
    """
    Whether `user` holds the rights for those actions - the call site form of `perms`.

    `match="any"` (the default, matching `has_perms`) passes on any one of the actions;
    `match="all"` demands every one. Keeps an OR rule to a single call instead of a
    chain of `has_perms`.
    """
    if match not in ("any", "all"):
        raise ValueError("match must be 'any' or 'all'")
    return user.has_perms(
        perms(entity, *actions), list_evaluation_or=(match == "any")
    )


# The `_perms` config keys, each mapped to the entity/action it carries. Single source
# for both the DEFAULT_CFG entries and the `_configure_permissions` assignments below,
# so a right cannot be declared in one and forgotten in the other - which is how
# `gql_query_users_profile_perms` came to sit in DEFAULT_CFG with right 122000 while
# never being assigned to `CoreConfig`, leaving it unreadable and its right
# unenforceable.
_PERM_CFG = {
    "gql_query_users_perms": ("user", "query"),
    "gql_query_users_profile_perms": ("user", "profile"),
    "gql_mutation_create_users_perms": ("user", "create"),
    "gql_mutation_update_users_perms": ("user", "update"),
    "gql_mutation_delete_users_perms": ("user", "delete"),
    "gql_query_roles_perms": ("role", "query"),
    "gql_mutation_create_roles_perms": ("role", "create"),
    "gql_mutation_update_roles_perms": ("role", "update"),
    "gql_mutation_replace_roles_perms": ("role", "replace"),
    "gql_mutation_duplicate_roles_perms": ("role", "duplicate"),
    "gql_mutation_delete_roles_perms": ("role", "delete"),
    "gql_query_enrolment_officers_perms": ("enrolmentOfficer", "query"),
    "gql_mutation_create_enrolment_officers_perms": ("enrolmentOfficer", "create"),
    "gql_mutation_update_enrolment_officers_perms": ("enrolmentOfficer", "update"),
    "gql_mutation_delete_enrolment_officers_perms": ("enrolmentOfficer", "delete"),
    "gql_query_claim_administrator_perms": ("claimAdministrator", "query"),
    "gql_mutation_create_claim_administrator_perms": ("claimAdministrator", "create"),
    "gql_mutation_update_claim_administrator_perms": ("claimAdministrator", "update"),
    "gql_mutation_delete_claim_administrator_perms": ("claimAdministrator", "delete"),
    "gql_query_enable_viewing_masked_data_perms": ("maskedData", "query"),
}

DEFAULT_CFG = {
    "username_code_length": "12",  # cannot be bigger than 50 unless modified length limit
    "username_changeable": True,
    "auto_provisioning_user_group": "user",
    "calendar_package": "core",
    "calendar_module": ".calendars.ad_calendar",
    "datetime_package": "core",
    "datetime_module": ".datetimes.ad_datetime",
    "shortstrfdate": "%d/%m/%Y",
    "longstrfdate": "%a %d %B %Y",
    "iso_raw_date": "False",
    "age_of_majority": "18",
    "async_mutations": (
        "True" if os.environ.get(
            "ASYNC",
            os.environ.get("MODE", "PROD")
        ).lower() == "prod" else "False"
    ),
    "password_reset_template": "password_reset.txt",
    "currency": "$",
    # Every `_perms` entry, derived from _PERM_CFG so the right ids live in exactly one
    # place (DJANGO_PERMS). An unknown entity or action raises here, at import time,
    # rather than silently yielding [] - which `has_perms` treats as "granted".
    **{key: perms(*entity_action) for key, entity_action in _PERM_CFG.items()},
    "fields_controls_user": {},
    "fields_controls_eo": {},
    "is_valid_health_facility_contract_required": False,
    "secondary_calendar": None,
    "locked_user_password_hash": "locked",
    "csrf_protect_login": True,
}


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"  # Django 3.1+
    name = MODULE_NAME
    username_code_length = 12
    username_changeable = True
    age_of_majority = 18
    password_reset_template = "password_reset.txt"

    # Pre-`ready()` placeholders for every _PERM_CFG key, so `CoreConfig.<key>` exists
    # (and denies nothing by accident) before the config is loaded. Declared explicitly
    # rather than generated, to stay greppable; _test_perm_cfg_matches_attributes keeps
    # the two lists in step.
    gql_query_roles_perms = []
    gql_mutation_create_roles_perms = []
    gql_mutation_update_roles_perms = []
    gql_mutation_replace_roles_perms = []
    gql_mutation_duplicate_roles_perms = []
    gql_mutation_delete_roles_perms = []
    gql_query_users_perms = []
    gql_query_users_profile_perms = []
    gql_mutation_create_users_perms = []
    gql_mutation_update_users_perms = []
    gql_mutation_delete_users_perms = []
    gql_query_enrolment_officers_perms = []
    gql_mutation_create_enrolment_officers_perms = []
    gql_mutation_update_enrolment_officers_perms = []
    gql_mutation_delete_enrolment_officers_perms = []
    gql_query_claim_administrator_perms = []
    gql_mutation_create_claim_administrator_perms = []
    gql_mutation_update_claim_administrator_perms = []
    gql_mutation_delete_claim_administrator_perms = []
    is_valid_health_facility_contract_required = None
    locked_user_password_hash = None

    fields_controls_user = {}
    fields_controls_eo = {}
    secondary_calendar = None

    password_min_length = settings.PASSWORD_MIN_LENGTH
    password_uppercase = settings.PASSWORD_UPPERCASE
    password_lowercase = settings.PASSWORD_LOWERCASE
    password_digits = settings.PASSWORD_DIGITS
    password_symbols = settings.PASSWORD_SYMBOLS

    # Deliberately sourced from settings (.env -> settings.py) and not from
    # DEFAULT_CFG: impersonation is a security kill-switch, so it must not be
    # flippable from the ModuleConfiguration table on a running production
    # instance. Defaults to off when the assembly does not define it.
    impersonation_enabled = getattr(settings, "IMPERSONATION_ENABLED", False)

    gql_query_enable_viewing_masked_data_perms = []

    csrf_protect_login = None

    def _import_module(self, cfg, k):
        logger.info("import %s.%s" % (cfg["%s_module" % k], cfg["%s_package" % k]))
        return importlib.import_module(
            cfg["%s_module" % k], package=cfg["%s_package" % k]
        )

    def _configure_calendar(self, cfg):
        this.shortstrfdate = cfg["shortstrfdate"]
        this.longstrfdate = cfg["longstrfdate"]
        this.iso_raw_date = (
            False
            if cfg["iso_raw_date"] is None
            else cfg["iso_raw_date"].lower() == "true"
        )
        try:
            this.calendar = self._import_module(cfg, "calendar")
            this.datetime = self._import_module(cfg, "datetime")
        except Exception:
            logger.error(
                "Failed to configure calendar, using default!\n%s: %s"
                % (sys.exc_info()[0].__name__, sys.exc_info()[1])
            )
            this.calendar = self._import_module(DEFAULT_CFG, "calendar")
            this.datetime = self._import_module(DEFAULT_CFG, "datetime")

    def _configure_user_config(self, cfg):
        this.username_code_length = int(cfg["username_code_length"])
        # Quick fix, this config has to be rebuilt
        CoreConfig.username_code_length = int(cfg["username_code_length"])
        CoreConfig.username_changeable = cfg["username_changeable"]

    def _configure_majority(self, cfg):
        this.age_of_majority = int(cfg["age_of_majority"])

    def _configure_currency(self, cfg):
        this.currency = str(cfg["currency"])

    def _configure_auto_provisioning(self, cfg):
        group = cfg["auto_provisioning_user_group"]
        this.auto_provisioning_user_group = group
        if not database_expected():
            logger.info(
                "No user auto provisioning: %s", unavailability_reason()
            )
            return

        with optional_database("create the %s auto provisioning group" % group, logger):
            from .models import Group

            g, _ = Group.objects.get_or_create(name=group)
            with optional_database(
                "adding the view_user permission to %s" % group, logger
            ):
                from django.contrib.auth.models import Permission

                # a row in auth_group_permissions, not a database GRANT.
                # auth's own post_migrate handler creates the Permission, so it
                # can still be missing the first time this runs on a fresh
                # database
                permission = Permission.objects.filter(codename="view_user").first()
                if permission:
                    g.permissions.add(permission)
                else:
                    logger.info(
                        "Permission view_user does not exist yet: %s left without it",
                        group,
                    )

    def _configure_graphql(self, cfg):
        this.async_mutations = (
            True
            if cfg["async_mutations"] is None
            else cfg["async_mutations"].lower() == "true"
        )

    def _configure_permissions(self, cfg):
        # Driven by _PERM_CFG rather than one assignment per right: adding a right to
        # DJANGO_PERMS + _PERM_CFG is now enough to have it read from config, and a key
        # can no longer be declared in DEFAULT_CFG yet never reach CoreConfig.
        for key in _PERM_CFG:
            value = cfg[key]
            if not value:
                # `has_perms([])` returns True: an empty right list grants the action to
                # everyone, authenticated or not. That is almost never intended, and a
                # silent one is how several queries ended up effectively public, so say
                # so loudly. Raising here instead would be the fail closed option, at
                # the cost of refusing to start on bad ModuleConfiguration data.
                logger.warning(
                    "core: %s resolved to an empty right list - `has_perms` treats that "
                    "as granted to everyone. Check the ModuleConfiguration override.",
                    key,
                )
            setattr(CoreConfig, key, value)

        CoreConfig.csrf_protect_login = cfg["csrf_protect_login"]

        CoreConfig.fields_controls_user = cfg["fields_controls_user"]
        CoreConfig.fields_controls_eo = cfg["fields_controls_eo"]

    def _configure_additional_settings(self, cfg):
        CoreConfig.is_valid_health_facility_contract_required = cfg[
            "is_valid_health_facility_contract_required"
        ]
        CoreConfig.secondary_calendar = cfg["secondary_calendar"]

    def _register_management_commands(self):
        # core loads after django.contrib.auth; get_commands() walks INSTALLED_APPS
        # in reverse and then earlier apps overwrite, so auth would win without this.
        from django.core.management import get_commands
        get_commands.cache_clear()
        get_commands()["createsuperuser"] = MODULE_NAME

    def ready(self):
        from .models import ModuleConfiguration

        self._register_management_commands()
        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CFG)
        self._configure_calendar(cfg)
        self._configure_user_config(cfg)
        self._configure_majority(cfg)
        self._configure_auto_provisioning(cfg)
        self._configure_graphql(cfg)
        self._configure_currency(cfg)
        self._configure_permissions(cfg)
        self._configure_additional_settings(cfg)

        CoreConfig.password_reset_template = cfg["password_reset_template"]
        CoreConfig.locked_user_password_hash = cfg["locked_user_password_hash"]

        # The scheduler starts as soon as it gets a job, which could be before Django is ready, so we enable it here
        from core import scheduler

        if settings.SCHEDULER_AUTOSTART:
            scheduler.start()
