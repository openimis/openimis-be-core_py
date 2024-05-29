import json
import logging
import os
import sys
import uuid
from copy import copy
from datetime import datetime as py_datetime, timedelta

from cached_property import cached_property
from dirtyfields import DirtyFieldsMixin
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Q, DO_NOTHING, F, JSONField
from django.utils.crypto import salted_hmac
from graphql import ResolveInfo
from pandas import DataFrame
from simple_history.models import HistoricalRecords

import core
from django.conf import settings

from .apps import CoreConfig
from .fields import DateTimeField
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


class BaseVersionedModel(models.Model):
    validity_from = DateTimeField(db_column='ValidityFrom', default=py_datetime.now)
    validity_to = DateTimeField(db_column='ValidityTo', blank=True, null=True)

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


class ExtendableModel(models.Model):
    json_ext = JSONField(
        db_column='JsonExt', blank=True, null=True)

    class Meta:
        abstract = True


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
        if bool(os.environ.get('NO_DATABASE', False)):
            logger.info('env NO_DATABASE set to True: ModuleConfiguration not loaded from db!')
            return default

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
        except Exception:
            logger.error('Failed to load %s configuration, using default!\n%s: %s' % (
                module, sys.exc_info()[0].__name__, sys.exc_info()[1]))
            return default

    @cached_property
    def _cfg(self):
        import collections
        return json.loads(self.config, object_pairs_hook=collections.OrderedDict)

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
        managed = True
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
        self._create_tech_user(username, email, password, **extra_fields)

    def create_superuser(self, username, password=None, email=None, **extra_fields):
        extra_fields['is_staff'] = True
        extra_fields['is_superuser'] = True
        self._create_tech_user(username, email, password, **extra_fields)

    def auto_provision_user(self, **kwargs):
        # only auto-provision django user if registered as interactive user
        try:
            i_user = InteractiveUser.objects.get(
                login_name=kwargs['username'],
                *filter_validity())
        except InteractiveUser.DoesNotExist:
            raise PermissionDenied
        user = self._create_core_user(**kwargs)
        user.i_user = i_user
        user.save()
        if core.auto_provisioning_user_group:
            group = Group.objects.get(
                name=core.auto_provisioning_user_group)
            user_group = UserGroup(user=user, group=group)
            user_group.save()
        return user, True

    def get_or_create(self, **kwargs):
        try:
            user = User.objects.get(**kwargs)
            return user, False
        except User.DoesNotExist:
            return self.auto_provision_user(**kwargs)


class TechnicalUser(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=CoreConfig.user_username_and_code_length_limit, unique=True)
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
    REQUIRED_FIELDS = ['password']

    def _bind_User(self):
        save_required = False
        try:
            usr = User.objects.get(t_user=self)
        except ObjectDoesNotExist:
            usr = User(username=self.username)
            usr.t_user = self
            save_required = True
        if usr.username != self.username:
            usr.username = self.username
            save_required = True
        if save_required:
            usr.shallow_save()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._bind_User()

    class Meta:
        managed = True
        db_table = 'core_TechnicalUser'


class Role(VersionedModel):
    id = models.AutoField(db_column='RoleID', primary_key=True)
    uuid = models.CharField(db_column='RoleUUID', max_length=36, default=uuid.uuid4, unique=True)
    name = models.CharField(db_column='RoleName', max_length=50)
    alt_language = models.CharField(
        db_column='AltLanguage', max_length=50, blank=True, null=True)
    is_system = models.IntegerField(db_column='IsSystem')
    is_blocked = models.BooleanField(db_column='IsBlocked')
    audit_user_id = models.IntegerField(
        db_column='AuditUserID', blank=True, null=True)

    @classmethod
    def get_queryset(cls, queryset, user):
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=-1)
        if settings.ROW_SECURITY:
            pass
        return queryset

    class Meta:
        managed = True
        db_table = 'tblRole'


class RoleRight(VersionedModel):
    id = models.AutoField(db_column='RoleRightID', primary_key=True)
    role = models.ForeignKey(Role, models.DO_NOTHING,
                             db_column='RoleID', related_name="rights")
    right_id = models.IntegerField(db_column='RightID')
    audit_user_id = models.IntegerField(
        db_column='AuditUserId', blank=True, null=True)

    @classmethod
    def get_queryset(cls, queryset, user):
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=-1)
        if settings.ROW_SECURITY:
            pass
        return queryset

    class Meta:
        managed = True
        db_table = 'tblRoleRight'


class InteractiveUser(VersionedModel):
    id = models.AutoField(db_column="UserID", primary_key=True)
    uuid = models.CharField(db_column="UserUUID", max_length=36, default=uuid.uuid4, unique=True)
    language = models.ForeignKey(Language, models.DO_NOTHING, db_column="LanguageID")
    last_name = models.CharField(db_column="LastName", max_length=100)
    other_names = models.CharField(db_column="OtherNames", max_length=100)
    phone = models.CharField(db_column="Phone", max_length=50, blank=True, null=True)
    login_name = models.CharField(db_column="LoginName", max_length=CoreConfig.user_username_and_code_length_limit)
    last_login = models.DateTimeField(db_column="LastLogin", null=True)
    health_facility_id = models.IntegerField(db_column="HFID", blank=True, null=True)

    audit_user_id = models.IntegerField(db_column="AuditUserID")
    # dummy_pwd is always blank. It is actually a transient field used in the Legacy to pass the clear text password in
    # a User object from the ASPX to the DAL where it is processed into/against password and private key/salt)
    # dummy_pwd = models.CharField(db_column='DummyPwd', max_length=25, blank=True, null=True)
    email = models.CharField(db_column="EmailId", max_length=200, blank=True, null=True)
    private_key = models.CharField(
        db_column="PrivateKey",
        max_length=256,
        blank=True,
        null=True,
        help_text="The private key is actually a password salt",
    )
    password = models.CharField(
        db_column="StoredPassword",
        max_length=256,
        blank=True,
        null=True,
        help_text="By default a SHA256 of the private key (salt) and password",
    )
    password_validity = models.DateTimeField(
        db_column="PasswordValidity", blank=True, null=True
    )
    is_associated = models.BooleanField(
        db_column="IsAssociated",
        blank=True,
        null=True,
        help_text="has a claim admin or enrolment officer account",
    )
    role_id = models.IntegerField(db_column="RoleID", null=False)

    @property
    def id_for_audit(self):
        return id

    @property
    def username(self):
        return self.login_name

    def get_username(self):
        return self.login_name

    @property
    def stored_password(self):
        return self.password

    @property
    def user(self):
        return self.user_set.first()

    @stored_password.setter
    def stored_password(self, value):
        logger.warn(
            "You should not use this property to set a password. Use 'password' instead."
        )
        self.password = value

    @property
    def is_staff(self):
        return False

    @property
    def is_superuser(self):
        if self.user and self.user.t_user:
            return self.user.t_user.is_superuser
        return False

    @cached_property
    def rights(self):
        return [rr.right_id for rr in RoleRight.filter_queryset().filter(
            role_id__in=[r.role_id for r in UserRole.filter_queryset().filter(
                user_id=self.id)]).distinct()]

    @cached_property
    def rights_str(self):
        return [str(r) for r in self.rights]

    @cached_property
    def health_facility(self):
        if self.health_facility_id:
            hf_model = apps.get_model("location", "HealthFacility")
            if hf_model:
                return hf_model.objects.filter(pk=self.health_facility_id).first()
        return None

    @property
    def is_officer(self):
        return Officer.objects.filter(
            code=self.username, has_login=True, validity_to__isnull=True).exists()

    @property
    def is_claim_admin(self):
        # Unlike Officer ClaimAdmin model was moved to the claim module,
        # and it's not granted that the module is installed.
        if 'claim' in sys.modules:
            from claim.models import ClaimAdmin
            return ClaimAdmin.objects.filter(
                code=self.username, has_login=True, validity_to__isnull=True).exists()
        else:
            return False

    @property
    def is_imis_admin(self):
        return Role.objects.filter(
                is_system=64,
                user_roles__user=self,
                validity_to__isnull=True,
                user_roles__validity_to__isnull=True,
                user_roles__user__validity_to__isnull=True
            ).exists()

    def set_password(self, raw_password):
        from hashlib import sha256
        from secrets import token_hex

        self.private_key = token_hex(128)
        pwd_hash = sha256()
        pwd_hash.update(f"{raw_password.rstrip()}{self.private_key}".encode())
        self.password = (
            pwd_hash.hexdigest().upper()
        )  # Legacy requires this to be uppercase

    def check_password(self, raw_password):
        from hashlib import sha256

        pwd_hash = sha256()
        pwd_hash.update(f"{raw_password.rstrip()}{self.private_key}".encode())
        pwd_hash = pwd_hash.hexdigest()
        # logger.debug("pwd_hash %s -> %s, stored: %s", f"{raw_password.rstrip()}{self.private_key}", pwd_hash, self.password)
        # hashlib gives a lowercase digest while the legacy gives an uppercase one
        return pwd_hash == self.password.lower()

    @classmethod
    def is_interactive_user(cls, user):
        if isinstance(user, InteractiveUser):
            return user
        elif isinstance(user, User) and user.i_user is not None:
            return user.i_user
        else:
            return None

    @classmethod
    def get_email_field_name(cls):
        return "email"

    @classmethod
    def get_queryset(cls, queryset, user):
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=-1)
        return queryset

    class Meta:
        managed = True
        db_table = 'tblUsers'


class UserRole(VersionedModel):
    id = models.AutoField(db_column='UserRoleID', primary_key=True)
    user = models.ForeignKey(
        InteractiveUser, models.DO_NOTHING, db_column='UserID', related_name="user_roles")
    role = models.ForeignKey(Role, models.DO_NOTHING,
                             db_column='RoleID', related_name="user_roles")
    audit_user_id = models.IntegerField(
        db_column='AudituserID', blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'tblUserRole'


class User(UUIDModel, PermissionsMixin, UUIDVersionedModel):
    username = models.CharField(unique=True, max_length=CoreConfig.user_username_and_code_length_limit)
    t_user = models.ForeignKey(TechnicalUser, on_delete=models.CASCADE, blank=True, null=True)
    i_user = models.ForeignKey(InteractiveUser, on_delete=models.CASCADE, blank=True, null=True)
    officer = models.ForeignKey("Officer", on_delete=models.CASCADE, blank=True, null=True)
    claim_admin = models.ForeignKey("claim.ClaimAdmin", on_delete=models.CASCADE, blank=True, null=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    objects = UserManager()

    @property
    def _u(self):
        return self.i_user or self.officer or self.claim_admin or self.t_user

    @property
    def id_for_audit(self):
        return self._u.id

    @property
    def last_login(self):
        return getattr(self._u, "last_login")

    @last_login.setter
    def last_login(self, value):
        return setattr(self._u, "last_login", value)

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
        if self.user and self.user.t_user:
            return self.user.t_user.is_superuser
        return False

    @property
    def is_imis_admin(self):
        # 64 is system number for IMIS Administrator
        user = self._u
        if isinstance(user, InteractiveUser):
            return user.is_imis_admin
        else:
            return False

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
        if i_user is not None and (i_user.is_superuser or perm in i_user.rights_str):
            return True
        else:
            return super(User, self).has_perm(perm, obj)

    @property
    def rights(self):
        if self.i_user:
            return self.i_user.rights
        return []

    def set_password(self, raw_password):
        if self._u and hasattr(self._u, "set_password"):
            return self._u.set_password(raw_password)
        self.clear_refresh_tokens()
        return None

    def clear_refresh_tokens(self):
        for refresh in self.refresh_tokens.filter(revoked__isnull=True):
            refresh.revoke()

    def get_session_auth_hash(self):
        key_salt = "core.User.get_session_auth_hash"
        return salted_hmac(key_salt, self.username).hexdigest()

    def get_health_facility(self):
        if self.claim_admin:
            return self.claim_admin.health_facility
        if self.i_user:
            return self.i_user.health_facility
        return None

    @property
    def health_facility(self):
        return self.get_health_facility()

    def __getattr__(self, name):
        if name == '_u':
            raise ValueError('wrapper has not been initialised')
        if name == '__name__':
            return self.username
        if name == 'get_session_auth_hash':
            return False
        return getattr(self._u, name)

    def __call__(self, *args, **kwargs):
        # if not self._u:
        #     raise ValueError('wrapper has not been initialised')
        if len(args) == 0 and len(kwargs) == 0 and not callable(self._u):
            # This happens when doing callable(user). Since this is a method, the class looks callable but it is not
            # To avoid this, we'll just return the object when calling it. This avoid issues in Django templates
            return self
        return self._u(*args, **kwargs)

    def __str__(self):
        if self.i_user:
            utype = 'i'
        elif self.t_user:
            utype = 't'
        elif self.officer:
            utype = 'o'
        elif self.claim_admin:
            utype = 'c'
        else:
            utype = '?'
        return "(%s) %s [%s]" % (utype, self.username, self.id)

    def save(self, *args, **kwargs):
        if self._u and self._u.id:
            self._u.save()
        super().save(*args, **kwargs)

    def shallow_save(self, *args, **kwargs):
        """ Unlike save(), shallow_save() won't attempt to save the subobjects, useful to avoid infinite recursion """
        super().save(*args, **kwargs)

    @classmethod
    def get_queryset(cls, queryset, user):
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=-1)
        if settings.ROW_SECURITY:
            pass
        return queryset

    def archive(self):
        from core import datetime
        self.validity_to = datetime.datetime.now()
        self.save()

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


class Officer(VersionedModel, ExtendableModel):
    id = models.AutoField(db_column='OfficerID', primary_key=True)
    uuid = models.CharField(db_column='OfficerUUID',
                            max_length=36, default=uuid.uuid4, unique=True)
    code = models.CharField(db_column='Code', max_length=CoreConfig.user_username_and_code_length_limit)
    last_name = models.CharField(db_column='LastName', max_length=100)
    other_names = models.CharField(db_column='OtherNames', max_length=100)
    dob = models.DateField(db_column='DOB', blank=True, null=True)
    phone = models.CharField(db_column='Phone', max_length=50, blank=True, null=True)
    location = models.ForeignKey('location.Location', models.DO_NOTHING, db_column='LocationId', blank=True, null=True)
    substitution_officer = models.ForeignKey('self', models.DO_NOTHING, db_column='OfficerIDSubst', blank=True,
                                             null=True)
    works_to = models.DateTimeField(db_column='WorksTo', blank=True, null=True)
    veo_code = models.CharField(db_column='VEOCode', max_length=CoreConfig.user_username_and_code_length_limit,
                                blank=True, null=True)
    veo_last_name = models.CharField(db_column='VEOLastName', max_length=100, blank=True, null=True)
    veo_other_names = models.CharField(db_column='VEOOtherNames', max_length=100, blank=True, null=True)
    veo_dob = models.DateField(db_column='VEODOB', blank=True, null=True)
    veo_phone = models.CharField(db_column='VEOPhone', max_length=25, blank=True, null=True)
    audit_user_id = models.IntegerField(db_column='AuditUserID')
    # rowid = models.TextField(db_column='RowID', blank=True, null=True)   This field type is a guess.
    email = models.CharField(db_column='EmailId', max_length=200, blank=True, null=True)
    phone_communication = models.BooleanField(db_column='PhoneCommunication', blank=True, null=True)
    address = models.CharField(db_column="permanentaddress", max_length=100, blank=True, null=True)
    has_login = models.BooleanField(db_column='HasLogin', blank=True, null=True)

    # user = models.ForeignKey(User, db_column='UserID', blank=True, null=True, on_delete=models.CASCADE)

    def name(self):
        return " ".join(n for n in [self.last_name, self.other_names] if n is not None)

    def __str__(self):
        return "[%s] %s" % (self.code, self.name())

    @property
    def id_for_audit(self):
        return id

    @property
    def username(self):
        return self.code

    def get_username(self):
        return self.code

    @property
    def is_staff(self):
        return False

    @property
    def is_superuser(self):
        return False

    @cached_property
    def rights(self):
        return []

    @cached_property
    def rights_str(self):
        return []

    def set_password(self, raw_password):
        raise NotImplementedError("Shouldn't set a password on an Officer")

    def check_password(self, raw_password):
        return False

    @property
    def officer_allowed_locations(self):
        """
        Returns uuid of all locations allowed for given officer
        """
        from location.models import OfficerVillage, Location
        villages = OfficerVillage.objects\
            .filter(officer=self, validity_to__isnull=True)
        all_allowed_uuids = []
        for village in villages:
            allowed_uuids = [village.location.uuid]
            parent = village.location.parent
            while parent is not None:
                allowed_uuids.append(parent.uuid)
                parent = parent.parent
            all_allowed_uuids.extend(allowed_uuids)
        return Location.objects.filter(uuid__in=all_allowed_uuids)

    @classmethod
    def get_queryset(cls, queryset, user):
        if isinstance(user, ResolveInfo):
            user = user.context.user
        if settings.ROW_SECURITY and user.is_anonymous:
            return queryset.filter(id=-1)
        return queryset

    class Meta:
        managed = True
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
    client_mutation_details = models.TextField(blank=True, null=True)
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
        affected_rows = MutationLog.objects.filter(id=self.id) \
            .filter(status=MutationLog.RECEIVED).update(status=MutationLog.SUCCESS)
        self.refresh_from_db()
        return affected_rows > 0

    def mark_as_failed(self, error):
        """
        Do not alter the mutation_log and then save it as it might override changes from another process.
        This method will force the status to ERROR and set its error accordingly.
        """
        MutationLog.objects.filter(id=self.id) \
            .update(status=MutationLog.ERROR, error=error)
        self.refresh_from_db()


class ObjectMutation:
    """
    This object is used for link tables between the business objects and the MutationLog like ClaimMutation.
    The object_mutated() method allows the creation of an object to update the xxxMutation easily.

    Declare the Mutation model as:
        class PaymentMutation(core_models.UUIDModel, core_models.ObjectMutation):
        payment = models.ForeignKey(Payment, models.DO_NOTHING, related_name='mutations')
        mutation = models.ForeignKey(core_models.MutationLog, models.DO_NOTHING, related_name='payments')

        class Meta:
            managed = True
            db_table = "contribution_PaymentMutation"

    Call it like:
        client_mutation_id = data.get("client_mutation_id")
        payment = update_or_create_payment(data, user)
        PaymentMutation.object_mutated(user, client_mutation_id=client_mutation_id, payment=payment)
        return None

    Note that payment=payment, the name of the parameter gives the field name of the xxxMutation object to use
    and the value is the instance itself.
    """

    @classmethod
    def object_mutated(cls, user, mutation_log_id=None, client_mutation_id=None, *args, **kwargs):
        # This method should fail silently to not disrupt the actual mutation
        # noinspection PyBroadException
        try:
            args_models = {k + "_id": v.id for k, v in kwargs.items() if isinstance(v, models.Model)}
            if len(args_models) == 0 or len(args_models) > 1:
                logger.error("Trying to update ObjectMutationLink with several models in params: %s",
                             ", ".join(args_models.keys()))
                return
            if mutation_log_id:
                cls.objects.get_or_create(mutation_id=mutation_log_id, **args_models)
            elif client_mutation_id:
                mutations = MutationLog.objects \
                                .filter(client_mutation_id=client_mutation_id) \
                                .filter(user=user) \
                                .values_list("id", flat=True) \
                                .order_by("-request_date_time")[:2]  # Only ask for 2 for the warning, we'll only use 1
                if len(mutations) == 2:
                    # Warning because if done too often, this would cause performance issues in this query
                    logger.warning("Two or more mutations found for id %s, using the most recent one",
                                   client_mutation_id)
                if len(mutations) == 0:
                    logger.debug("No mutation found for client_mutation_id %s, ignoring", client_mutation_id)
                    return
                cls.objects.get_or_create(mutation_id=mutations[0], **args_models)
            else:
                logger.warning(
                    "Trying to update a %s without either mutation id or client_mutation_id, ignoring", cls.__name__)
        except Exception as exc:
            # The mutation shouldn't fail because we couldn't store the UUID
            logger.error("Error updating the %s object", cls.__name__, exc_info=True)


class HistoryModelManager(models.Manager):
    """
        Custom manager that allows querying HistoryModel by uuid
    """

    def get_queryset(self):
        return super().get_queryset().annotate(uuid=F('id'))


class HistoryModel(DirtyFieldsMixin, models.Model):
    id = models.UUIDField(primary_key=True, db_column="UUID", default=None, editable=False)
    objects = HistoryModelManager()
    is_deleted = models.BooleanField(db_column="isDeleted", default=False)
    json_ext = models.JSONField(db_column="Json_ext", blank=True, null=True)
    date_created = DateTimeField(db_column="DateCreated", null=True)
    date_updated = DateTimeField(db_column="DateUpdated", null=True)
    user_created = models.ForeignKey(User, db_column="UserCreatedUUID", related_name='%(class)s_user_created',
                                     on_delete=models.deletion.DO_NOTHING, null=False)
    user_updated = models.ForeignKey(User, db_column="UserUpdatedUUID", related_name='%(class)s_user_updated',
                                     on_delete=models.deletion.DO_NOTHING, null=False)
    version = models.IntegerField(default=1)
    history = HistoricalRecords(
        inherit=True,
    )

    @property
    def uuid(self):
        return self.id

    @uuid.setter
    def uuid(self, v):
        self.id = v

    def set_pk(self):
        self.pk = uuid.uuid4()

    def save_history(self):
        pass

    def save(self, *args, **kwargs):
        # get the user data so as to assign later his uuid id in fields user_updated etc
        if 'username' in kwargs:
            user = User.objects.get(username=kwargs.pop('username'))
        else:
            raise ValidationError('Save error! Provide the username of the current user in `username` argument')
        from core import datetime
        now = datetime.datetime.now()
        # check if object has been newly created
        if self.id is None:
            # save the new object
            self.set_pk()
            self.user_created = user
            self.user_updated = user
            self.date_created = now
            self.date_updated = now
            return super(HistoryModel, self).save(*args, **kwargs)
        if self.is_dirty(check_relationship=True):
            self.date_updated = now
            self.user_updated = user
            self.version = self.version + 1
            # check if we have business model
            if hasattr(self, "replacement_uuid"):
                if self.replacement_uuid is not None and 'replacement_uuid' not in self.get_dirty_fields():
                    raise ValidationError('Update error! You cannot update replaced entity')
            return super(HistoryModel, self).save(*args, **kwargs)
        else:
            raise ValidationError('Record has not be updated - there are no changes in fields')

    def delete_history(self):
        pass

    def delete(self, *args, **kwargs):
        if 'username' in kwargs:
            user = User.objects.get(username=kwargs.pop('username'))
        else:
            raise ValidationError('Delete error! Provide the username of the current user in `username` argument')
        if not self.is_dirty(check_relationship=True) and not self.is_deleted:
            from core import datetime
            now = datetime.datetime.now()
            self.date_updated = now
            self.user_updated = user
            self.version = self.version + 1
            self.is_deleted = True
            # check if we have business model
            if hasattr(self, "replacement_uuid"):
                # When a replacement entity is deleted, the link should be removed
                # from replaced entity so a new replacement could be generated
                replaced_entity = self.__class__.objects.filter(replacement_uuid=self.id).first()
                if replaced_entity:
                    replaced_entity.replacement_uuid = None
                    replaced_entity.save(username="admin")
            return super(HistoryModel, self).save(*args, **kwargs)
        else:
            raise ValidationError(
                'Record has not be deactivating, the object is different and must be updated before deactivating')

    @classmethod
    def filter_queryset(cls, queryset=None):
        if queryset is None:
            queryset = cls.objects.all()
        queryset = queryset.filter()
        return queryset

    class Meta:
        abstract = True


class HistoryBusinessModel(HistoryModel):
    date_valid_from = DateTimeField(db_column="DateValidFrom", default=py_datetime.now)
    date_valid_to = DateTimeField(db_column="DateValidTo", blank=True, null=True)
    replacement_uuid = models.UUIDField(db_column="ReplacementUUID", null=True)

    def replace_object(self, data, **kwargs):
        # check if object was created and saved in database (having date_created field)
        if self.id is None:
            return None
        user = User.objects.get(**kwargs)
        # 1 step - create new entity
        new_entity = self._create_new_entity(user=user, data=data)
        # 2 step - update the fields for the entity to be replaced
        self._update_replaced_entity(user=user, uuid_from_new_entity=new_entity.id,
                                     date_valid_from_new_entity=new_entity.date_valid_from)

    def _create_new_entity(self, user, data):
        """1 step - create new entity"""
        from core import datetime
        now = datetime.datetime.now()
        new_entity = copy(self)
        new_entity.id = None
        new_entity.version = 1
        new_entity.date_valid_from = now
        new_entity.date_valid_to = None
        new_entity.replacement_uuid = None
        # replace the fiedls if there are any to update in new entity
        if "uuid" in data:
            data.pop('uuid')
        if len(data) > 0:
            [setattr(new_entity, key, data[key]) for key in data]
        if self.date_valid_from is None:
            raise ValidationError('Field date_valid_from should not be empty')
        new_entity.save(username=user.username)
        return new_entity

    def _update_replaced_entity(self, user, uuid_from_new_entity, date_valid_from_new_entity):
        """2 step - update the fields for the entity to be replaced"""
        # convert to datetime if the date_valid_from from new entity is date
        from core import datetime
        if not isinstance(date_valid_from_new_entity, datetime.datetime):
            date_valid_from_new_entity = datetime.datetime.combine(
                date_valid_from_new_entity,
                datetime.datetime.min.time()
            )
        if not self.is_dirty(check_relationship=True):
            if self.date_valid_to is not None:
                if date_valid_from_new_entity < self.date_valid_to:
                    self.date_valid_to = date_valid_from_new_entity
            else:
                self.date_valid_to = date_valid_from_new_entity
            self.replacement_uuid = uuid_from_new_entity
            self.save(username=user.username)
            return self
        else:
            raise ValidationError("Object is changed - it must be updated before being replaced")

    class Meta:
        abstract = True


class RoleMutation(UUIDModel, ObjectMutation):
    role = models.ForeignKey(Role, models.DO_NOTHING,
                             related_name='mutations')
    mutation = models.ForeignKey(
        MutationLog, models.DO_NOTHING, related_name='roles')

    class Meta:
        managed = True
        db_table = "core_RoleMutation"


class UserMutation(UUIDModel, ObjectMutation):
    core_user = models.ForeignKey(User, models.CASCADE, related_name='mutations')
    mutation = models.ForeignKey(MutationLog, models.DO_NOTHING, related_name='users')

    class Meta:
        managed = True
        db_table = "core_UserMutation"


def _get_default_expire_date():
    return py_datetime.now() + timedelta(days=1)


def _query_export_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return F'query_exports/user_{instance.user.uuid}/{filename}'


class ExportableQueryModel(models.Model):
    name = models.CharField(max_length=255)
    model = models.CharField(max_length=255)
    content = models.FileField(upload_to=_query_export_path)

    user = models.ForeignKey(
        User, db_column="User", related_name='data_exports',
        on_delete=models.deletion.DO_NOTHING, null=False)

    sql_query = models.TextField()
    create_date = DateTimeField(db_column='DateCreated', default=py_datetime.now)
    expire_date = DateTimeField(db_column='DateExpiring', default=_get_default_expire_date)
    is_deleted = models.BooleanField(default=False)

    @staticmethod
    def create_csv_export(qs, values, user, column_names=None,
                          patches=None):
        if patches is None:
            patches = []
        sql = qs.query.sql_with_params()
        content = DataFrame.from_records(qs.values_list(*values))
        content.columns = values
        for patch in patches:
            content = patch(content)

        content.columns = column_names or values
        filename = F"{uuid.uuid4()}.csv"
        content = ContentFile(content.to_csv(), filename)
        export = ExportableQueryModel(
            name=filename,
            model=qs.model,
            content=content,
            user=user,
            sql_query=sql,
        )
        export.save()
        return export
