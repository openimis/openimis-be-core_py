import sys
import os
import importlib
import logging
from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)

MODULE_NAME = "core"

this = sys.modules[MODULE_NAME]

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
    "async_mutations": "True" if os.environ.get("ASYNC", os.environ.get("MODE", "PROD")) == "PROD" else "False",
    "password_reset_template": "password_reset.txt",
    "currency": "$",
    "gql_query_users_perms": ["121701"],
    "gql_mutation_create_users_perms": ["121702"],
    "gql_mutation_update_users_perms": ["121703"],
    "gql_mutation_delete_users_perms": ["121704"],
    "gql_query_roles_perms": ["122001"],
    "gql_mutation_create_roles_perms": ["122002"],
    "gql_mutation_update_roles_perms": ["122003"],
    "gql_mutation_replace_roles_perms": ["122006"],
    "gql_mutation_duplicate_roles_perms": ["122005"],
    "gql_mutation_delete_roles_perms": ["122004"],
    # TODO consider moving that roles related to ClaimAdmin and EnrolmentOfficer
    #  into modules related to that type of user for example
    #  EnrolmentOfficer -> policy module, ClaimAdmin -> claim module etc
    "gql_query_enrolment_officers_perms": ["121501"],
    "gql_mutation_create_enrolment_officers_perms": ["121502"],
    "gql_mutation_update_enrolment_officers_perms": ["121503"],
    "gql_mutation_delete_enrolment_officers_perms": ["121504"],
    "gql_query_claim_administrator_perms": ["121601"],
    "gql_mutation_create_claim_administrator_perms": ["121602"],
    "gql_mutation_update_claim_administrator_perms": ["121603"],
    "gql_mutation_delete_claim_administrator_perms": ["121604"],
    "fields_controls_user": {},
    "fields_controls_eo": {},
    "is_valid_health_facility_contract_required": False,
    "secondary_calendar": None,
    "locked_user_password_hash": 'locked',
    "gql_query_enable_viewing_masked_data_perms": ["900101"],
    "csrf_protect_login": True,
}


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.AutoField'  # Django 3.1+
    name = MODULE_NAME
    username_code_length = 12
    username_changeable = True
    age_of_majority = 18
    password_reset_template = "password_reset.txt"
    gql_query_roles_perms = []
    gql_mutation_create_roles_perms = []
    gql_mutation_update_roles_perms = []
    gql_mutation_replace_roles_perms = []
    gql_mutation_duplicate_roles_perms = []
    gql_mutation_delete_roles_perms = []
    gql_query_users_perms = []
    gql_mutation_create_users_perms = []
    gql_mutation_update_users_perms = []
    gql_mutation_delete_users_perms = []
    # TODO consider moving that roles related to ClaimAdmin and EnrolmentOfficer
    #  into modules related to that type of user for example
    #  EnrolmentOfficer -> policy module, ClaimAdmin -> claim module etc
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

    gql_query_enable_viewing_masked_data_perms = []

    csrf_protect_login = None

    def _import_module(self, cfg, k):
        logger.info('import %s.%s' %
                    (cfg["%s_module" % k], cfg["%s_package" % k]))
        return importlib.import_module(
            cfg["%s_module" % k], package=cfg["%s_package" % k])

    def _configure_calendar(self, cfg):
        this.shortstrfdate = cfg["shortstrfdate"]
        this.longstrfdate = cfg["longstrfdate"]
        this.iso_raw_date = False if cfg["iso_raw_date"] is None else cfg["iso_raw_date"].lower(
        ) == "true"
        try:
            this.calendar = self._import_module(cfg, "calendar")
            this.datetime = self._import_module(cfg, "datetime")
        except Exception:
            logger.error('Failed to configure calendar, using default!\n%s: %s' % (
                sys.exc_info()[0].__name__, sys.exc_info()[1]))
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
        if bool(os.environ.get('NO_DATABASE', False)):
            logger.info('env NO_DATABASE set to True: no user auto provisioning possible!')
            return
        group = cfg["auto_provisioning_user_group"]
        this.auto_provisioning_user_group = group
        try:
            from .models import Group
            Group.objects.get(name=group)
        except Group.DoesNotExist:
            g = Group(name=group)
            g.save()
            from django.contrib.auth.models import Permission
            p = Permission.objects.get(codename="view_user")
            g.permissions.add(p)
            g.save()
        except Exception as e:
            logger.warning('Failed set auto_provisioning_user_group ' + str(e))

    def _configure_graphql(self, cfg):
        this.async_mutations = True if cfg["async_mutations"] is None else cfg["async_mutations"].lower() == "true"

    def _configure_permissions(self, cfg):
        CoreConfig.gql_query_roles_perms = cfg["gql_query_roles_perms"]
        CoreConfig.gql_mutation_create_roles_perms = cfg["gql_mutation_create_roles_perms"]
        CoreConfig.gql_mutation_update_roles_perms = cfg["gql_mutation_update_roles_perms"]
        CoreConfig.gql_mutation_replace_roles_perms = cfg["gql_mutation_replace_roles_perms"]
        CoreConfig.gql_mutation_duplicate_roles_perms = cfg["gql_mutation_duplicate_roles_perms"]
        CoreConfig.gql_mutation_delete_roles_perms = cfg["gql_mutation_delete_roles_perms"]
        CoreConfig.gql_query_users_perms = cfg["gql_query_users_perms"]
        CoreConfig.gql_mutation_create_users_perms = cfg["gql_mutation_create_users_perms"]
        CoreConfig.gql_mutation_update_users_perms = cfg["gql_mutation_update_users_perms"]
        CoreConfig.gql_mutation_delete_users_perms = cfg["gql_mutation_delete_users_perms"]
        CoreConfig.gql_query_enrolment_officers_perms = cfg["gql_query_enrolment_officers_perms"]
        CoreConfig.gql_mutation_create_enrolment_officers_perms = cfg["gql_mutation_create_enrolment_officers_perms"]
        CoreConfig.gql_mutation_update_enrolment_officers_perms = cfg["gql_mutation_update_enrolment_officers_perms"]
        CoreConfig.gql_mutation_delete_enrolment_officers_perms = cfg["gql_mutation_delete_enrolment_officers_perms"]
        CoreConfig.gql_query_claim_administrator_perms = cfg["gql_query_claim_administrator_perms"]
        CoreConfig.gql_mutation_create_claim_administrator_perms = cfg["gql_mutation_create_claim_administrator_perms"]
        CoreConfig.gql_mutation_update_claim_administrator_perms = cfg["gql_mutation_update_claim_administrator_perms"]
        CoreConfig.gql_mutation_delete_claim_administrator_perms = cfg["gql_mutation_delete_claim_administrator_perms"]
        CoreConfig.gql_mutation_delete_claim_administrator_perms = cfg["gql_mutation_delete_claim_administrator_perms"]
        CoreConfig.gql_query_enable_viewing_masked_data_perms = cfg["gql_query_enable_viewing_masked_data_perms"]
        CoreConfig.csrf_protect_login = cfg["csrf_protect_login"]

        CoreConfig.fields_controls_user = cfg["fields_controls_user"]
        CoreConfig.fields_controls_eo = cfg["fields_controls_eo"]

    def _configure_additional_settings(self, cfg):
        CoreConfig.is_valid_health_facility_contract_required = cfg["is_valid_health_facility_contract_required"]
        CoreConfig.secondary_calendar = cfg["secondary_calendar"]

    def ready(self):
        from .models import ModuleConfiguration
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
