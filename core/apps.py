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
    "date_package": "core",
    "date_module": ".dates.ad_date",
    "date_class": "AdDate",
    "shortstrfdate": "%d/%m/%Y",
    "longstrfdate": "%a %d %B %Y",
}


class CoreConfig(AppConfig):
    name = MODULE_NAME

    def _import_module(self, cfg, k):
        return importlib.import_module(
            cfg["%s_module" % k], package=cfg["%s_package" % k])

    def _import_class(self, cfg, k):
        return getattr(self._import_module(cfg, k), cfg["%s_class" % k])

    def _configure_calendar(self, cfg):
        this.shortstrfdate = cfg["shortstrfdate"]
        this.longstrfdate = cfg["longstrfdate"]
        try:
            this.calendar = self._import_module(cfg, "calendar")
            this.date = self._import_class(cfg, "date")            
        except:
            logger.error('Failed to configure calendar, using default!\n%s: %s' % (
                sys.exc_info()[0].__name__, sys.exc_info()[1]))
            this.calendar = self._import_module(DEFAULT_CFG, "calendar")
            this.date = self._import_class(DEFAULT_CFG, "date")
        print("date class is %s" % this.date)

    def ready(self):
        from .models import ModuleConfiguration
        cfg = ModuleConfiguration.get_or_default(
            MODULE_NAME, DEFAULT_CFG)
        self._configure_calendar(cfg)
