import sys
import json
import logging
import uuid
from django.db import models
from cached_property import cached_property
from .fields import DateField, DateTimeField

logger = logging.getLogger(__name__)

"""
Abstract entity, parent of all (new) openIMIS entities.
Enforces the UUID identifier.
"""


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

    def __str__(self):
        return "[%s]" % (self.id)


"""
Generic entity to save every modules' configuration (json format)
"""


class ModuleConfiguration(UUIDModel):
    module = models.CharField(max_length=20)
    version = models.CharField(max_length=10)
    config = models.TextField()

    @classmethod
    def get_or_default(cls, module, default):
        try:
            db_configuration = cls.objects.get(module=module)._cfg
            return {**default, **db_configuration}
        except ModuleConfiguration.DoesNotExist:
            logger.info('No %s configuration, using default!' % module)
            return default
        except:
            logger.error('Failed to load %s configuration, using default!\n%s: %s' % (
                module, sys.exc_info()[0].__name__, sys.exc_info()[1]))
            return default

    @cached_property
    def _cfg(self):
        return json.loads(self.config)

    def __str__(self):
        return "%s [%s]" % (self.module, self.version)

    class Meta:
        db_table = 'core_ModuleConfiguration'


class Language(models.Model):
    code = models.CharField(db_column='LanguageCode',
                            primary_key=True, max_length=2)
    name = models.CharField(db_column='LanguageName', max_length=50)
    sort_order = models.IntegerField(
        db_column='SortOrder', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tblLanguages'


class User(models.Model):
    id = models.AutoField(db_column='UserID', primary_key=True)
    legacy_id = models.IntegerField(
        db_column='LegacyID', blank=True, null=True)
    language_id = models.ForeignKey(
        Language, models.DO_NOTHING, db_column='LanguageID')
    last_name = models.CharField(db_column='LastName', max_length=100)
    other_names = models.CharField(db_column='OtherNames', max_length=100)
    phone = models.CharField(
        db_column='Phone', max_length=50, blank=True, null=True)
    login_name = models.CharField(db_column='LoginName', max_length=25)
    role_id = models.IntegerField(db_column='RoleID')
    health_facility_id = models.IntegerField(
        db_column='HFID', blank=True, null=True)
    validity_from = DateTimeField(db_column='ValidityFrom')
    validity_to = DateTimeField(db_column='ValidityTo', blank=True, null=True)

    audit_user_id = models.IntegerField(db_column='AuditUserID')
    # password = models.BinaryField(blank=True, null=True)
    # dummy_pwd = models.CharField(db_column='DummyPwd', max_length=25, blank=True, null=True)
    email_id = models.CharField(
        db_column='EmailId', max_length=200, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tblUsers'
