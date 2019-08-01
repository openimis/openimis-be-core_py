import sys
import json
import logging
import uuid
from django.db import models
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from cached_property import cached_property
from .fields import DateField, DateTimeField
from datetime import datetime as py_datetime

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


class Control(models.Model):
    field_name = models.CharField(db_column='FieldName', primary_key=True, max_length=50)
    adjustibility = models.CharField(db_column='Adjustibility', max_length=1)
    usage = models.CharField(db_column='Usage', max_length=200, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tblControls'


"""
Generic entity to save every modules' configuration (json format)
"""


class ModuleConfiguration(UUIDModel):
    module = models.CharField(max_length=20)
    MODULE_LAYERS = [('fe', 'frontend'), ('be', 'backend')]
    layer = models.CharField(
        max_length=2,
        choices=MODULE_LAYERS,
        default='be',
    )
    version = models.CharField(max_length=10)
    config = models.TextField()
    # is_exposed indicates wherever a configuration is safe to be accessible from api
    # DON'T EXPOSE (backend) configurations that contain credentials,...
    is_exposed = models.BooleanField(default=False)
    is_disabled_until = models.DateTimeField(
        default=None,
        blank=True,
        null=True
    )

    @classmethod
    def get_or_default(cls, module, default, layer='be'):
        try:
            now = py_datetime.now()  # can't use core config here...
            db_configuration = cls.objects.get(
                Q(is_disabled_until=None) | Q(is_disabled_until__lt=now),
                layer=layer,
                module=module
            )._cfg
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


class UserManager(BaseUserManager):

    def _create_tech_user(self, username, email, password, **extra_fields):
        tech = TechnicalUser(username=username, email=email, **extra_fields)
        tech.set_password(password)
        tech.save()
        return tech

    def create_user(self, username, password, email=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields['is_superuser'] = False
        self._create_tech_user(
            username, email, password, **extra_fields)

    def create_superuser(self, username, password, email=None, **extra_fields):
        extra_fields['is_staff'] = True
        extra_fields['is_superuser'] = True
        self._create_tech_user(
            username, email, password, **extra_fields)


class TechnicalUser(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True, null=True)
    language_id = 'en'
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    validity_from = models.DateTimeField(blank=True, null=True)
    validity_to = models.DateTimeField(blank=True, null=True)

    USERNAME_FIELD = 'username'

    def _bind_User(self):
        save_required = False
        try:
            usr = User.objects.get(t_user=self)
        except ObjectDoesNotExist:
            usr = User()
            usr.t_user = self
            save_required = True
        if usr.username != self.username:
            usr.username = self.username
            save_required = True
        if save_required:
            usr.save()

    def save(self):
        super().save()
        self._bind_User()

    class Meta:
        managed = True
        db_table = 'core_TechnicalUser'


class InteractiveUser(models.Model):
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
    email = models.CharField(
        db_column='EmailId', max_length=200, blank=True, null=True)
    # private_key = models.CharField(db_column='PrivateKey', max_length=256, blank=True, null=True)
    # stored_password = models.CharField(db_column='StoredPassword', max_length=256, blank=True, null=True)
    # password_validity = models.DateTimeField(db_column='PasswordValidity', blank=True, null=True)
    # is_associated = models.BooleanField(db_column='IsAssociated', blank=True, null=True)

    def save(self, *args, **kwargs):
        # exclusively managed from legacy openIMIS for now!
        raise NotImplementedError()

    @property
    def username(self):
        return self.login_name

    @property
    def is_staff(self):
        return False

    @property
    def is_superuser(self):
        return False

    def set_password(self, raw_password):
        # exclusively managed from legacy openIMIS for now!
        raise NotImplementedError()

    def check_password(self, raw_password):
        # exclusively managed from legacy openIMIS for now!
        raise NotImplementedError()

    class Meta:
        managed = False
        db_table = 'tblUsers'


class User(UUIDModel, PermissionsMixin):
    username = models.CharField(unique=True, max_length=25)
    t_user = models.ForeignKey(
        TechnicalUser, on_delete=models.CASCADE, blank=True, null=True)
    i_user = models.ForeignKey(
        InteractiveUser, on_delete=models.CASCADE, blank=True, null=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __init__(self, *args, **kwargs):
        super(User, self).__init__(*args, **kwargs)
        self._u = self.i_user or self.t_user

    @property
    def is_anonymous(self):
        return False

    @property
    def is_authenticated(self):
        return True

    @property
    def is_staff(self):
        return self._u.is_staff

    @property
    def is_superuser(self):
        return self._u.is_superuser

    @property
    def is_active(self):
        if self._u.validity_from is None and self._u.validity_to is None:
            return True
        from core import datetime
        now = datetime.datetime.now()
        if not self._u.validity_from is None and self._u.validity_from > now:
            return False
        if not self._u.validity_to is None and self._u.validity_to < now:
            return False
        return True

    def __getattr__(self, name):
        if name == '_u':
            raise ValueError('wrapper has not been initialised')
        if name == '__name__':
            return self.username
        if not self._u:
            return None
        return getattr(self._u, name)

    def __call__(self, *args, **kwargs):
        # if not self._u:
        #     raise ValueError('wrapper has not been initialised')
        return self._u(*args, **kwargs)

    def __str__(self):
        return "(%s) %s [%s]" % (('i' if self.i_user else 't'), self.username, self.id)

    class Meta:
        managed = True
        db_table = 'core_User'
