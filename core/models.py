import sys
import json
import logging
import uuid
from copy import copy

import core
from django.db import models
from django.db.models import Q, DO_NOTHING
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group
from django.utils.crypto import salted_hmac
from cached_property import cached_property
from .fields import DateTimeField
from datetime import datetime as py_datetime
from .utils import filter_validity

logger = logging.getLogger(__name__)


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


class ModuleConfiguration(UUIDModel):
    """
    Generic entity to save every modules' configuration (json format)
    """
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


class FieldControl(UUIDModel):
    module = models.ForeignKey(
        ModuleConfiguration, models.DO_NOTHING, related_name='controls')
    field = models.CharField(unique=True, max_length=250)
    # mask: Hidden | Readonly | Mandatory
    usage = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'core_FieldControl'


class Language(models.Model):
    code = models.CharField(db_column='LanguageCode',
                            primary_key=True, max_length=5)
    name = models.CharField(db_column='LanguageName', max_length=50)
    sort_order = models.IntegerField(
        db_column='SortOrder', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tblLanguages'


class UserManager(BaseUserManager):

    def _create_core_user(self, **fields):
        user = User(**fields)
        user.save()
        return user

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

    def get_or_create(self, **kwargs):
        created = False
        try:
            user = User.objects.get(**kwargs)
        except User.DoesNotExist:
            created = True
            user = self._create_core_user(**kwargs)
        if user._u is None:
            try:
                user.i_user = InteractiveUser.objects.get(
                    login_name=user.username,
                    *filter_validity())
            except InteractiveUser.DoesNotExist:
                raise Exception("Unauthorized")
            user.save()
            if core.auto_provisioning_user_group:
                group = Group.objects.get(
                    name=core.auto_provisioning_user_group)
                user_group = UserGroup(user=user, group=group)
                user_group.save()
        return user, created


class TechnicalUser(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True, null=True)
    language = 'en'
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    validity_from = models.DateTimeField(blank=True, null=True)
    validity_to = models.DateTimeField(blank=True, null=True)

    @property
    def id_for_audit(self):
        return -1

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._bind_User()

    class Meta:
        managed = True
        db_table = 'core_TechnicalUser'


class Role(models.Model):
    id = models.AutoField(db_column='RoleID', primary_key=True)
    uuid = models.CharField(db_column='RoleUUID', max_length=36)
    name = models.CharField(db_column='RoleName', max_length=50)
    altlanguage = models.CharField(
        db_column='AltLanguage', max_length=50, blank=True, null=True)
    is_system = models.IntegerField(db_column='IsSystem')
    is_blocked = models.BooleanField(db_column='IsBlocked')
    validity_from = models.DateTimeField(db_column='ValidityFrom')
    validity_to = models.DateTimeField(
        db_column='ValidityTo', blank=True, null=True)
    audit_user_id = models.IntegerField(
        db_column='AuditUserID', blank=True, null=True)
    legacy_id = models.IntegerField(
        db_column='LegacyID', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tblRole'


class RoleRight(models.Model):
    id = models.AutoField(db_column='RoleRightID', primary_key=True)
    role = models.ForeignKey(Role, models.DO_NOTHING,
                             db_column='RoleID', related_name="rights")
    right_id = models.IntegerField(db_column='RightID')
    validity_from = models.DateTimeField(db_column='ValidityFrom')
    validity_to = models.DateTimeField(
        db_column='ValidityTo', blank=True, null=True)
    audit_user_id = models.IntegerField(
        db_column='AuditUserId', blank=True, null=True)
    legacy_id = models.IntegerField(
        db_column='LegacyID', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tblRoleRight'


class InteractiveUser(models.Model):
    id = models.AutoField(db_column='UserID', primary_key=True)
    uuid = models.CharField(db_column='UserUUID',
                            max_length=36, default=uuid.uuid4, unique=True)
    legacy_id = models.IntegerField(
        db_column='LegacyID', blank=True, null=True)
    language = models.ForeignKey(
        Language, models.DO_NOTHING, db_column='LanguageID')
    last_name = models.CharField(db_column='LastName', max_length=100)
    other_names = models.CharField(db_column='OtherNames', max_length=100)
    phone = models.CharField(
        db_column='Phone', max_length=50, blank=True, null=True)
    login_name = models.CharField(db_column='LoginName', max_length=25)
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

    @property
    def id_for_audit(self):
        return id

    def save(self, *args, **kwargs):
        # exclusively managed from legacy openIMIS for now!
        raise NotImplementedError()

    @property
    def username(self):
        return self.login_name

    def get_username(self):
        return self.login_name

    @property
    def is_staff(self):
        return False

    @property
    def is_superuser(self):
        return False

    @cached_property
    def rights(self):
        return [rr.right_id for rr in RoleRight.objects.filter(
            role_id__in=[r.role_id for r in UserRole.objects.filter(
                user_id=self.id)]).distinct()]

    @cached_property
    def rights_str(self):
        return [str(r) for r in self.rights]

    def set_password(self, raw_password):
        # exclusively managed from legacy openIMIS for now!
        raise NotImplementedError()

    def check_password(self, raw_password):
        # exclusively managed from legacy openIMIS for now!
        raise NotImplementedError()

    class Meta:
        managed = False
        db_table = 'tblUsers'


class UserRole(models.Model):
    id = models.AutoField(db_column='UserRoleID', primary_key=True)
    user = models.ForeignKey(
        InteractiveUser, models.DO_NOTHING, db_column='UserID', related_name="user_roles")
    role = models.ForeignKey(Role, models.DO_NOTHING,
                             db_column='RoleID', related_name="user_roles")
    validity_from = models.DateTimeField(db_column='ValidityFrom')
    validity_to = models.DateTimeField(
        db_column='ValidityTo', blank=True, null=True)
    audit_user_id = models.IntegerField(
        db_column='AudituserID', blank=True, null=True)
    legacy_id = models.IntegerField(
        db_column='LegacyID', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tblUserRole'


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
    def id_for_audit(self):
        return self._u.id

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

    def has_perm(self, perm, obj=None):
        i_user = self.i_user if obj is None else obj.i_user
        return True if i_user is not None and perm in i_user.rights_str else super(User, self).has_perm(perm, obj)

    def get_session_auth_hash(self):
        key_salt = "core.User.get_session_auth_hash"
        return salted_hmac(key_salt, self.username).hexdigest()

    def __getattr__(self, name):
        if name == '_u':
            raise ValueError('wrapper has not been initialised')
        if name == '__name__':
            return self.username
        if name == 'get_session_auth_hash':
            return False
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


class UserGroup(models.Model):
    user = models.ForeignKey(User, models.DO_NOTHING)
    group = models.ForeignKey(Group, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'core_User_groups'
        unique_together = (('user', 'group'),)


class Officer(models.Model):
    id = models.AutoField(db_column='OfficerID', primary_key=True)
    uuid = models.CharField(db_column='OfficerUUID',
                            max_length=36, default=uuid.uuid4, unique=True)
    code = models.CharField(db_column='Code', max_length=8)
    last_name = models.CharField(db_column='LastName', max_length=100)
    other_names = models.CharField(db_column='OtherNames', max_length=100)
    # dob = models.DateField(db_column='DOB', blank=True, null=True)
    # phone = models.CharField(db_column='Phone', max_length=50, blank=True, null=True)
    # location = models.ForeignKey(Tbllocations, models.DO_NOTHING, db_column='LocationId', blank=True, null=True)
    # officeridsubst = models.ForeignKey('self', models.DO_NOTHING, db_column='OfficerIDSubst', blank=True, null=True)
    # worksto = models.DateTimeField(db_column='WorksTo', blank=True, null=True)
    # veocode = models.CharField(db_column='VEOCode', max_length=8, blank=True, null=True)
    # veolastname = models.CharField(db_column='VEOLastName', max_length=100, blank=True, null=True)
    # veoothernames = models.CharField(db_column='VEOOtherNames', max_length=100, blank=True, null=True)
    # veodob = models.DateField(db_column='VEODOB', blank=True, null=True)
    # veophone = models.CharField(db_column='VEOPhone', max_length=25, blank=True, null=True)
    # audituserid = models.IntegerField(db_column='AuditUserID')
    # rowid = models.TextField(db_column='RowID', blank=True, null=True)   This field type is a guess.
    # emailid = models.CharField(db_column='EmailId', max_length=200, blank=True, null=True)
    # phonecommunication = models.BooleanField(db_column='PhoneCommunication', blank=True, null=True)
    # permanentaddress = models.CharField(max_length=100, blank=True, null=True)
    # haslogin = models.BooleanField(db_column='HasLogin', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tblOfficer'


class MutationLog(UUIDModel):
    """
    Maintains a log of every mutation requested along with its status. It is used to reply
    immediately to the client and have longer processing in the various backend modules.
    The ID of this table will be used for reference.
    """
    RECEIVED = 0
    ERROR = 1
    SUCCESS = 2
    STATUS_CHOICES = (
        (RECEIVED, "Received"),
        (ERROR, "Error"),
        (SUCCESS, "Success"),
    )

    json_content = models.TextField()
    user = models.ForeignKey(User, on_delete=DO_NOTHING, blank=True, null=True)
    request_date_time = models.DateTimeField(auto_now_add=True)
    client_mutation_id = models.CharField(
        max_length=255, blank=True, null=True)
    client_mutation_label = models.CharField(
        max_length=255, blank=True, null=True)
    status = models.IntegerField(choices=STATUS_CHOICES, default=RECEIVED)
    error = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = "core_Mutation_Log"

    def mark_as_successful(self):
        """
        Do not alter the mutation_log and then save it as it might override changes from another process. This
        method will only set the mutation_log as successful if it is in RECEIVED status.
        :return True if the status was updated, False if it was in ERROR or already in SUCCESS status
        """
        affected_rows = MutationLog.objects.filter(id=self.id)\
            .filter(status=MutationLog.RECEIVED).update(status=MutationLog.SUCCESS)
        self.refresh_from_db()
        return affected_rows > 0

    def mark_as_failed(self, error):
        """
        Do not alter the mutation_log and then save it as it might override changes from another process.
        This method will force the status to ERROR and set its error accordingly.
        """
        MutationLog.objects.filter(id=self.id)\
            .update(status=MutationLog.ERROR, error=error)
        self.refresh_from_db()


class VersionedModel(models.Model):
    legacy_id = models.IntegerField(
        db_column='LegacyID', blank=True, null=True)
    validity_from = DateTimeField(db_column='ValidityFrom')
    validity_to = DateTimeField(db_column='ValidityTo', blank=True, null=True)

    def save_history(self, **kwargs):
        if not self.id: # only copy if the data is being updated
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
