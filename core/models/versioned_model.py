import uuid
from copy import copy
from datetime import datetime as py_datetime
from django.core.cache import caches
from django.db import models

from core.utils import (
    clear_cache,
    get_cache_key
)
from ..fields import DateTimeField
from ..utils import filter_validity
import logging

logger = logging.getLogger(__name__)
CACHE_TIMEOUT = 3600 * 24
cache = caches["default"]


class CachedManager(models.Manager):
    
    def get(self, *args, **kwargs):
        """
        Overrides the get() method to check Redis cache before
        performing a DB lookup for simple unique lookups.
        """
        unique_fields = ('pk', 'id', 'uuid')
        cache_key = None

        # Case 1: Simple kwargs lookup.
        if kwargs and len(kwargs) == 1:
            key = list(kwargs.keys())[0]
            if key in unique_fields:
                value = kwargs[key]
                # Convert UUID objects to string for the cache key.
                if key in ('id', 'pk'):
                    try:
                        # Convert to int if possible.
                        value = int(value)
                    except (ValueError, TypeError):
                        pass
                if isinstance(value, uuid.UUID):
                    value = str(value)
                cache_key = get_cache_key(self.__class__, value)
        # use case for Family Request elements in args
        elif not kwargs and args and len(args) == 1 :
            if len(args[0].children) == 1:
                field, value = args[0].children[0]
                if field in unique_fields:
                    cache_key = get_cache_key(self.__class__, value)

        # If we constructed a cache key, try to retrieve from the cache.
        if cache_key:
            cached_instance = cache.get(cache_key)
            if cached_instance is not None:
                logger.debug("Returning cached instance for key: %s", cache_key)
                return cached_instance

            # Not in cache; perform DB lookup.
        instance = super().get(*args, **kwargs)
        cache.set(cache_key, instance, timeout=None)
        logger.debug("Cached instance %s after DB lookup", cache_key)
        return instance


class BaseVersionedModel(models.Model):
    validity_from = DateTimeField(db_column='ValidityFrom', default=py_datetime.now)
    validity_to = DateTimeField(db_column='ValidityTo', blank=True, null=True)

    # Use our custom CachedManager for object retrieval
    objects = CachedManager()

    def update(self, *args, **kwargs):
        """
        Overrides the default update to update the cache after saving the instance.
        """
        super().update(*args, **kwargs)
        cache.set(get_cache_key(self.__class__, self.id), self,  timeout=CACHE_TIMEOUT)

    def save(self, *args, **kwargs):
        """
        Overrides the default save to update the cache after saving the instance.
        """
        caching = kwargs.pop('cache_update', True)
        super().save(*args, **kwargs)
        if caching:
            # Build the cache key using the same logic as in the CachedManager.
            # (Assuming lookups are done using pk/id/uuid)
            cache.set(get_cache_key(self.__class__, self.id), self,  timeout=CACHE_TIMEOUT)
            logger.debug("Saved and cached instance: %s", self)
        else:
            clear_cache(self)
        return self

    def delete(self, *args, **kwargs):
        """
        Overrides the default delete to remove the instance from the cache.
        """
        # Build the cache key prior to deletion.
        clear_cache(self)
        logger.debug("Clear cached instance: %s", self)
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

    @classmethod
    def filter_queryset(cls, queryset=None):
        if queryset is None:
            queryset = cls.objects.all()
        queryset = queryset.filter(*filter_validity())
        return queryset




class VersionedModel(BaseVersionedModel):
    legacy_id = models.IntegerField(
        db_column='LegacyID', blank=True, null=True)



    class Meta:
        abstract = True


class UUIDVersionedModel(BaseVersionedModel):
    legacy_id = models.UUIDField(
        db_column='LegacyID', blank=True, null=True)

    class Meta:
        abstract = True


