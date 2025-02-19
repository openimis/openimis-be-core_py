import logging
import sys
import uuid
from datetime import timedelta, datetime as py_datetime
from django.core.cache import cache
from cached_property import cached_property
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import models
from django.utils.crypto import salted_hmac
from graphql import ResolveInfo
import core


# from core.utils import validate_password
from django.contrib.auth.password_validation import validate_password
#from core.datetimes.ad_datetime import datetime as py_datetime
from django.conf import settings

from ..utils import filter_validity
from .base import *
from .versioned_model import *

logger = logging.getLogger(__name__)
from rest_framework import exceptions


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
        except InteractiveUser.DoesNotExist as e:
            raise exceptions.AuthenticationFailed("INCORRECT_CREDENTIALS") from e
        user = self._create_core_user(**kwargs)
        user.i_user = i_user
        user.save()
        if core.auto_provisioning_user_group:
            group = Group.objects.filter(
                name=core.auto_provisioning_user_group).first()
            if group:
                user_group = UserGroup(user=user, group=group)
                user_group.save()
            else:
                logger.error(f"Group {core.auto_provisioning_user_group} was not found")
        return user, True

    def get_or_create(self, **kwargs):
        user = User.objects.filter(username__iexact=kwargs.get("username")).first()
        if user:
            return user, False
        else:
            return self.auto_provision_user(**kwargs)


class TechnicalUser(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(blank=True, null=True)
    language = 'en'
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    validity_from = models.DateTimeField(blank=True, null=True, default = py_datetime.now)
    validity_to = models.DateTimeField(blank=True, null=True)
    is_imis_admin = False
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
    login_name = models.CharField(db_column="LoginName", max_length=50)
    last_login = models.DateTimeField(db_column="LastLogin", null=True, blank=True)
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
    # deprecated
    role_id = models.IntegerField(db_column="RoleID", null=True, blank=True)

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
        return self.is_superuser


    @property
    def is_superuser(self):
        return self.is_imis_admin



    @property
    def rights(self):
        rights = cache.get('rights_' + str(self.id))
        if rights:
            return rights
        rights = [rr.right_id for rr in RoleRight.filter_queryset().filter(
            role_id__in=[r.role_id for r in UserRole.filter_queryset().filter(
                user_id=self.id)]).distinct()]
        cache.set('rights_' + str(self.id), rights, timeout=None)
        return rights

    @property
    def rights_str(self):
        rights = [str(r) for r in self.rights]
        return rights

    @cached_property
    def health_facility(self):
        if self.health_facility_id:
            hf_model = apps.get_model("location", "HealthFacility")
            if hf_model:
                return hf_model.objects.filter(pk=self.health_facility_id).first()
        return None

    @property
    def is_officer(self):
        cache_name = f"user_eo_{self.login_name}"
        is_officer = cache.get(cache_name)
        if is_officer is None:
            is_officer = Officer.objects.filter(
                code=self.login_name,
                has_login=True,
                *filter_validity()
            ).exists()
            cache.set(cache_name, is_officer, None)
        return is_officer

    @property
    def is_claim_admin(self):
        # Unlike Officer ClaimAdmin model was moved to the claim module,
        # and it's not granted that the module is installed.
        if 'claim' in sys.modules:
            cache_name = f"user_ca_{self.login_name}"
            is_claim_admin = cache.get(cache_name)
            if is_claim_admin is None:
                
                from claim.models import ClaimAdmin
                is_claim_admin = ClaimAdmin.objects.filter(
                    code=self.login_name,
                    has_login=True,
                    *filter_validity()
                ).exists()
                cache.set(cache_name, is_claim_admin, None)
            return is_claim_admin
        else:
            return False

    @property
    def is_imis_admin(self):
        is_admin = cache.get('is_admin_' + str(self.id))
        if is_admin is None:
            is_admin = Role.objects.filter(
                is_system=64,
                user_roles__user=self,
                validity_to__isnull=True,
                user_roles__validity_to__isnull=True,
                user_roles__user__validity_to__isnull=True
            ).exists()
            cache.set('is_admin_' + str(self.id), is_admin, 600)
        return is_admin

    def set_password(self, raw_password):
        from hashlib import sha256
        from secrets import token_hex
        validate_password(raw_password)
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
    username = models.CharField(unique=True, max_length=50)
    t_user = models.ForeignKey(TechnicalUser, on_delete=models.CASCADE, blank=True, null=True)
    i_user = models.ForeignKey(InteractiveUser, on_delete=models.CASCADE, blank=True, null=True)
    officer = models.ForeignKey("Officer", on_delete=models.CASCADE, blank=True, null=True)
    claim_admin = models.ForeignKey("claim.ClaimAdmin", on_delete=models.CASCADE, blank=True, null=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save_history(self, **kwargs):
        # Prevent from saving history. It would lead to error due to username uniqueness.
        pass

    def delete_history(self, **kwargs):
        now = py_datetime.now()
        self.validity_from = now
        self.validity_to = now
        self.save()

    @property
    def _u(self):
        return self.i_user or self.officer or self.claim_admin or self.t_user

    def has_perms(self, perm_list, obj=None, list_evaluation_or=True):
        if not perm_list:
            return True
        if self.is_imis_admin:
            return True
        elif list_evaluation_or:
            return any(self.has_perm(perm, obj) for perm in perm_list)
        else:
            return super().has_perms(perm_list, obj)

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
        return self._u.is_superuser

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
        now = py_datetime.now()
        if not self._u.validity_from is None and self._u.validity_from > now:
            return False
        if not self._u.validity_to is None and self._u.validity_to < now:
            return False
        return True

    def has_perm(self, perm, obj=None):
        i_user = self.i_user if obj is None else obj.i_user
        if i_user is not None and (
            i_user.is_superuser or 
            any(str(right) == perm for right in i_user.rights)
        ):
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
        elif name == '__name__':
            return self.username
        elif name == 'get_session_auth_hash':
            return False
        elif hasattr(self._u, name):
            return getattr(self._u, name)
        elif name in self.__dict__:
            return self.__dict__[name]
        else:
            raise AttributeError(f"User has no attribute {name}")
        
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
    code = models.CharField(db_column='Code', max_length=50)
    last_name = models.CharField(db_column='LastName', max_length=100)
    other_names = models.CharField(db_column='OtherNames', max_length=100)
    dob = models.DateField(db_column='DOB', blank=True, null=True)
    phone = models.CharField(db_column='Phone', max_length=50, blank=True, null=True)
    location = models.ForeignKey('location.Location', models.DO_NOTHING, db_column='LocationId', blank=True, null=True)
    substitution_officer = models.ForeignKey('self', models.DO_NOTHING, db_column='OfficerIDSubst', blank=True,
                                             null=True)
    works_to = models.DateTimeField(db_column='WorksTo', blank=True, null=True)
    veo_code = models.CharField(db_column='VEOCode', max_length=50, blank=True, null=True)
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

    

def _get_default_expire_date():
    return py_datetime.now() + timedelta(days=1)


def _query_export_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return F'query_exports/user_{instance.user.uuid}/{filename}'

