import copy
import json
import logging
import uuid

from datetime import datetime as py_datetime
import datetime as base_datetime
from cached_property import cached_property
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, JSONField

from core.bootstrap import (
    database_expected,
    optional_database,
    unavailability_reason,
)
from core.module_config_registry import validate_module_configuration, reload_module_configuration

# from core.datetimes.ad_datetime import datetime as py_datetime


logger = logging.getLogger(__name__)


class ExtendableModel(models.Model):
    json_ext = JSONField(db_column="JsonExt", blank=True, null=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """
    Abstract entity, parent of all (new) openIMIS entities.
    Enforces the UUID identifier.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

    def __str__(self):
        return "[%s]" % (self.id,)

    @property
    def uuid(self):
        return self.id

    @uuid.setter
    def uuid(self, value):
        self.id = value


class ModuleConfiguration(UUIDModel):
    """
    Generic entity to save every modules' configuration (json format)
    """

    module = models.CharField(max_length=80)
    MODULE_LAYERS = [("fe", "frontend"), ("be", "backend")]
    layer = models.CharField(
        max_length=2,
        choices=MODULE_LAYERS,
        default="be",
    )
    version = models.CharField(max_length=10)
    config = models.TextField()
    # is_exposed indicates wherever a configuration is safe to be accessible from api
    # DON'T EXPOSE (backend) configurations that contain credentials,...
    is_exposed = models.BooleanField(default=False)
    is_disabled_until = models.DateTimeField(default=None, blank=True, null=True)

    @classmethod
    def get_or_default(cls, module, default, layer="be"):
        defaults = copy.deepcopy(default)
        if not database_expected():
            logger.info(
                "Not loading the %s configuration from the database: %s",
                module,
                unavailability_reason(),
            )
            return defaults

        configuration = defaults
        # runs from every AppConfig.ready(), so the table may not exist yet
        with optional_database(
            "loading the %s configuration, using defaults" % module,
            logger,
            tolerate_all=True,
        ):
            now = py_datetime.now()  # can't use core config here...
            qs = cls.objects.filter(
                Q(is_disabled_until=None) | Q(is_disabled_until__lt=now),
                layer=layer,
                module=module,
            ).first()
            if qs:
                configuration = {**defaults, **qs._cfg}
            else:
                logger.info("No %s configuration, using default!" % module)
        return configuration

    @cached_property
    def _cfg(self):
        import collections

        return json.loads(self.config, object_pairs_hook=collections.OrderedDict)

    def clean(self):
        super().clean()

        try:
            self._cfg
        except (TypeError, json.JSONDecodeError) as e:
            raise ValidationError({"config": f"Invalid JSON: {e}"})

        validate_module_configuration(self)

    def save(self, *args, **kwargs):
        # `_cfg` is a cached_property, so it keeps parsing the config string it
        # saw first. Reassigning `config` on an instance that has already been
        # validated or saved would otherwise validate - and reload the module
        # with - the *previous* configuration.
        self.__dict__.pop("_cfg", None)
        self.clean()
        super().save(*args, **kwargs)
        transaction.on_commit(lambda: reload_module_configuration(self))

    def __str__(self):
        return "%s [%s]" % (self.module, self.version)

    class Meta:
        db_table = "core_ModuleConfiguration"


class FieldControl(UUIDModel):
    module = models.ForeignKey(
        ModuleConfiguration, models.DO_NOTHING, related_name="controls"
    )
    field = models.CharField(unique=True, max_length=250)
    # mask: Hidden | Readonly | Mandatory
    usage = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = "core_FieldControl"


class Language(models.Model):
    code = models.CharField(db_column="LanguageCode", primary_key=True, max_length=5)
    name = models.CharField(db_column="LanguageName", max_length=50)
    sort_order = models.IntegerField(db_column="SortOrder", blank=True, null=True)

    class Meta:
        managed = True
        db_table = "tblLanguages"


def resolved_id_reference(instance, data):
    return resolve_id_reference(instance, data)


def resolve_id_reference(instance, data):
    out = {}
    for k, v in data.items():
        found = False
        if k.endswith("_id") and v:
            if hasattr(instance, k[:-3]):
                field = instance._meta.get_field(k[:-3])
                try:
                    out[k[:-3]] = field.remote_field.model.objects.get(pk=v)
                    found = True
                except Exception as e:
                    logger.debug(e)
                    raise Exception(
                        f"{instance.__name__}: relationship from {field.remote_field.model.__name__} : {v} not found "
                    )
        if not found:
            field = instance._meta.get_field(k)
            if isinstance(field, (base_datetime.date, base_datetime.datetime)):
                v = py_datetime.strptime(v, "%Y-%m-%d")
            out[k] = v
    return out
