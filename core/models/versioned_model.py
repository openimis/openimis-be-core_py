import uuid
from copy import copy
from datetime import datetime as py_datetime

from django.db import models
from django.db.models import Q

from core.utils import CachedManager, CachedModelMixin
from ..fields import DateTimeField
from ..utils import filter_validity as core_filter_validity
import logging
from core.models.row_security import RowSecurityMixin
from core.models.row_filters import NO_ROWS, Audits, day_bounds

logger = logging.getLogger(__name__)


class BaseVersionedModel(RowSecurityMixin, CachedModelMixin, models.Model):
    validity_from = DateTimeField(db_column="ValidityFrom", default=py_datetime.now)
    validity_to = DateTimeField(db_column="ValidityTo", blank=True, null=True)

    # Use our custom CachedManager for object retrieval
    objects = CachedManager()

    @staticmethod
    def filter_validity(validity=None, prefix="", **kwargs):
        return core_filter_validity(validity=validity, prefix=prefix, **kwargs)

    def update(self, *args, **kwargs):
        """
        Overrides the default update to update the cache after saving the instance.
        """
        obj_data = kwargs.pop("data", None)
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        [setattr(self, key, obj_data[key]) for key in obj_data]
        self.save(*args, **kwargs)

    def save(self, *args, **kwargs):
        """
        Overrides the default save to update the cache after saving the instance.
        """
        caching = kwargs.pop("cache_update", True)
        super(BaseVersionedModel, self).save(*args, **kwargs)
        if caching:
            # Build the cache key using the same logic as in the CachedManager.
            # (Assuming lookups are done using pk/id/uuid)
            self.update_cache()
        else:
            self.delete_cache()
        return self

    def delete(self, *args, **kwargs):
        """
        Overrides the default delete to remove the instance from the cache.
        """
        # Build the cache key prior to deletion.
        self.delete_cache()
        # Then perform the actual deletion.
        return super().delete(*args, **kwargs)

    def save_history(self, **kwargs):
        if not self.id:  # only copy if the data is being updated
            return None
        histo = copy(self)
        histo.id = None
        if hasattr(histo, "uuid"):
            setattr(histo, "uuid", uuid.uuid4())
        histo.validity_to = py_datetime.now()
        histo.legacy_id = self.id
        histo.save(cache_update=False)
        return histo.id

    def delete_history(self, **kwargs):
        self.save_history()
        now = py_datetime.now()
        self.validity_from = now
        self.validity_to = now
        self.save()

    class Meta:
        abstract = True

    #: True on the tables whose versions carry a business meaning (price
    #: lists, products, health facilities...): a validity date then picks the
    #: version valid at that date. Elsewhere versions are an audit trail only.
    business_versioned = False

    @classmethod
    def get_business_validity_fields(cls):
        return ("validity_from", "validity_to") if cls.business_versioned else None

    @classmethod
    def live_rows_q(cls):
        return Q(validity_to__isnull=True)

    @classmethod
    def _has_legacy_id(cls):
        return any(field.name == "legacy_id" for field in cls._meta.fields)

    @classmethod
    def current_rows_q(cls):
        # save_history() copies the row with legacy_id pointing at it;
        # delete_history() closes validity_to on the row itself.
        return Q(legacy_id__isnull=True) if cls._has_legacy_id() else None

    @classmethod
    def dated_rows_q(cls):
        # The version valid at a date may be an audit copy by now.
        return Q()

    @classmethod
    def audit_rows_q(cls, audits):
        if not cls._has_legacy_id():
            return NO_ROWS
        copies = Q(legacy_id__isnull=False)
        if audits == Audits.ALL:
            return copies
        start, end = day_bounds(*audits.range())
        if audits.kind == "at":
            return copies & Q(validity_from__lte=end, validity_to__gte=start)
        # An audit copy is dated by the change that superseded it.
        if start is not None:
            copies &= Q(validity_to__gte=start)
        if end is not None:
            copies &= Q(validity_to__lte=end)
        return copies

    @classmethod
    def filter_queryset(cls, queryset=None):
        if queryset is None:
            queryset = cls.objects.all()
        queryset = queryset.filter(*core_filter_validity())
        return queryset


class VersionedModel(BaseVersionedModel):
    legacy_id = models.IntegerField(db_column="LegacyID", blank=True, null=True)

    class Meta:
        abstract = True


class UUIDVersionedModel(BaseVersionedModel):
    legacy_id = models.UUIDField(db_column="LegacyID", blank=True, null=True)

    class Meta:
        abstract = True
