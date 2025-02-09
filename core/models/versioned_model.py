import uuid
from copy import copy
from datetime import datetime as py_datetime
from django.core.cache import caches
from django.db import models
#from core.datetimes.ad_datetime import datetime as py_datetime

from ..fields import DateTimeField
from ..utils import filter_validity
import logging
import datetime

logger = logging.getLogger(__name__)

cache = caches["default"]

class CachedManager(models.Manager):

    def flatten_q(self, q_obj):
        """
        Recursively flattens a Q object into a list of lookup tuples.
        """
        conditions = []

        print("q_obj", q_obj)
        print("q_obj.children", q_obj.children)
        for child in q_obj.children:
            if isinstance(child, Q):
                conditions.extend(self.flatten_q(child))
            else:
                conditions.append(child)
        return conditions
    
    def get(self, *args, **kwargs):
        """
        Overrides the get() method to check Redis cache before
        performing a DB lookup for simple unique lookups.
        """
        print("Get on Cached Manager")
        print(kwargs)
        print(args)
        
        unique_fields = ('pk','id','uuid')
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
                cache_key = f"{self.model.__name__}:{value}"
                print("cache_key", cache_key)
        # use case for Family Request elements in args
        elif not kwargs and args and len(args) == 1 :
            if len(args[0].children) == 1:
                field, value = args[0].children[0]
                if field in unique_fields:
                    cache_key = f"{self.model.__name__}:{value}"
                    print("cache_key", cache_key)

        # If we constructed a cache key, try to retrieve from the cache.
        if cache_key:
            cached_instance = cache.get(cache_key)
            if cached_instance is not None:
                print("cached_instance", cached_instance)
                print("Returning cached instance for key: %s", cache_key)
                logger.debug("Returning cached instance for key: %s", cache_key)
                return cached_instance

            # Not in cache; perform DB lookup.
            instance = super().get(*args, **kwargs)
            cache.set(cache_key, instance, timeout=None)
            print("Cached instance %s after DB lookup", cache_key)
            logger.debug("Cached instance %s after DB lookup", cache_key)
            return instance

        # Fallback: if the lookup is not a simple unique one, use the default get().
        return super().get(*args, **kwargs)

class BaseVersionedModel(models.Model):
    validity_from = DateTimeField(db_column='ValidityFrom', default=py_datetime.now)
    validity_to = DateTimeField(db_column='ValidityTo', blank=True, null=True)

    # Use our custom CachedManager for object retrieval
    objects = CachedManager()

    def get_cache_key(self):
        """
        Generates a unique cache key for an instance based on the model’s class name and primary key.
        """
        if not self.pk:
            return None
        return f"{self.__class__.__name__}:{self.pk}"

    def save(self, *args, **kwargs):
        """
        Override save() so that after saving the instance to the DB, it is also cached.
        """
        super().save(*args, **kwargs)
        cache_key = self.get_cache_key()
        if cache_key:
            cache.set(cache_key, self, timeout=self.CACHE_TIMEOUT)
            logger.debug("Saved and cached instance: %s", cache_key)

    def delete(self, *args, **kwargs):
        """
        Override delete() so that before deleting the instance, the corresponding cache entry is removed.
        """
        cache_key = self.get_cache_key()
        if cache_key:
            cache.delete(cache_key)
            logger.debug("Deleted cache entry for: %s", cache_key)
        super().delete(*args, **kwargs)

    def save_history(self, **kwargs):
        if not self.id:  # only copy if the data is being updated
            return None
        histo = copy(self)
        histo.id = None
        if hasattr(histo, "uuid"):
            setattr(histo, "uuid", uuid.uuid4())
        from core import datetime
        histo.validity_to = datetime.datetime.now()
        histo.legacy_id = self.id
        histo.save()
        return histo.id

    def delete_history(self, **kwargs):
        self.save_history()
        from core import datetime
        now = datetime.datetime.now()
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

    @classmethod
    def get_by_pk(cls, pk):
        """
        Utility method to fetch an instance by primary key. This method first
        attempts to retrieve the instance from the Redis cache; if not found,
        it retrieves it from the database and then caches it.
        """
        cache_key = f"{cls.__name__}:{pk}"
        instance = cache.get(cache_key)
        if instance is None:
            try:
                instance = cls.objects.get(pk=pk)
                cache.set(cache_key, instance, timeout=cls.CACHE_TIMEOUT)
                logger.debug(f"Cached instance {cache_key} after DB lookup")
            except cls.DoesNotExist:
                return None
        return instance


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


