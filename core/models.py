import sys
import json
import logging
from django.db import models
from cached_property import cached_property

logger = logging.getLogger(__name__)

"""
Generic entity to save every modules' configuration (json format)
"""
class ModuleConfiguration(models.Model):
    module = models.CharField(max_length=20)
    version = models.CharField(max_length=10)
    config = models.CharField(max_length=1024)

    @classmethod
    def get_or_default(cls, module, default):
        try:
            db_configuration = cls.objects.get(module=module)._cfg
            return {**default, **db_configuration}
        except ModuleConfiguration.DoesNotExist:
            logger.info('No %s configuration, using default!' % module)
            return default
        except:
            logger.error('Failed to load %s configuration, using default!\n%s: %s' % (module, sys.exc_info()[0].__name__,sys.exc_info()[1]))
            return default

    
    @cached_property
    def _cfg(self):
        return json.loads(self.config)

    def __str__(self):
        return "%s [%s]" % (self.module, self.version)

    class Meta:
        db_table = 'core_ModuleConfiguration'
