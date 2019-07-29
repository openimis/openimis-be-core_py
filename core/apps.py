import sys
import importlib
import json
import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)

MODULE_NAME = "core"

this = sys.modules[MODULE_NAME]

DEFAULT_CFG = {
    "calendar_package": "core",
    "calendar_module": ".calendars.ad_calendar",
    "datetime_package": "core",
    "datetime_module": ".datetimes.ad_datetime",
    "shortstrfdate": "%d/%m/%Y",
    "longstrfdate": "%a %d %B %Y",
    "iso_raw_date": "False",
}


class CoreConfig(AppConfig):
    name = MODULE_NAME

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
        except:
            logger.error('Failed to configure calendar, using default!\n%s: %s' % (
                sys.exc_info()[0].__name__, sys.exc_info()[1]))
            this.calendar = self._import_module(DEFAULT_CFG, "calendar")
            this.datetime = self._import_module(DEFAULT_CFG, "datetime")

    def ready(self):
        from .models import ModuleConfiguration
        cfg = ModuleConfiguration.get_or_default(
            MODULE_NAME, DEFAULT_CFG)
        self._configure_calendar(cfg)
