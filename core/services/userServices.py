import hashlib
#
import logging
from gettext import gettext as _

from django.apps import apps
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail, BadHeaderError
from django.template import loader
from django.utils.html import escape
from django.utils.http import urlencode
from django.core.cache import cache
from core.apps import CoreConfig
from core.models.user import User, InteractiveUser, Officer, UserRole, UserManager
from core.validation.obligatoryFieldValidation import (
    validate_payload_for_obligatory_fields,
)
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import exceptions
from django.db.models import Q

logger = logging.getLogger(__file__)


def create_or_update_interactive_user(user_id, data, user_maker, connected):
    admin = User.objects.filter(i_user_id=1).first()
    if not admin:
        User.objects.create(username="Admin", i_user_id=1)
    i_fields = {
        "username": "login_name",
        "other_names": "other_names",
        "last_name": "last_name",
        "phone": "phone",
        "email": "email",
        "language": "language_id",
        "health_facility_id": "health_facility_id",
    }
    data_subset = {v: data.get(k) for k, v in i_fields.items()}
    data_subset["is_associated"] = connected
    if user_id:
        # TODO we might want to update a user that has been deleted. Use Legacy ID ?
        i_user = InteractiveUser.objects.filter(
            validity_to__isnull=True, user__id=user_id
        ).first()
        if i_user.validity_to is not None and i_user.validity_to:
            raise ValidationError(_("core.user.edit_historical_data_error"))
    else:
        i_user = InteractiveUser.objects.filter(
            validity_to__isnull=True, login_name=data_subset["login_name"]
        ).first()
    if i_user:
        i_user.save_history()
        [setattr(i_user, k, v) for k, v in data_subset.items()]
        if "password" in data:
            i_user.set_password(data["password"])
        created = False
    else:
        i_user = InteractiveUser(**data_subset)
        if "password" in data:
            i_user.set_password(data["password"])
        else:
            # No password provided for creation, will have to be set later.
            i_user.stored_password = CoreConfig.locked_user_password_hash
        created = True

    i_user.save()
    create_or_update_user_roles(i_user, data["roles"], user_maker.id_for_audit)
    if "districts" in data:
        create_or_update_user_districts(
            i_user, data["districts"], user_maker.id_for_audit
        )
    cache.delete("cs_InteractiveUserSerializer_" + str(i_user.id))
    return i_user, created


def create_or_update_user_roles(i_user, role_ids, audit_user_id):
    import datetime

    now = datetime.datetime.now()
    UserRole.objects.filter(user=i_user, validity_to__isnull=True).update(
        validity_to=now
    )
    for role_id in role_ids:
        UserRole.objects.create(
            user=i_user, role_id=role_id, audit_user_id=audit_user_id
        )
    cache.delete("rights_" + str(i_user.id))
    cache.delete("is_admin_" + str(i_user.id))
    cache.delete("cs_InteractiveUserSerializer_" + str(i_user.id))


# TODO move to location module ?
def create_or_update_user_districts(i_user, district_ids, audit_user_id):
    # To avoid a static dependency from Core to Location, we'll dynamically load this class
    user_district_class = apps.get_model("location", "UserDistrict")
    import datetime

    now = datetime.datetime.now()
    user_district_class.objects.filter(user=i_user, validity_to__isnull=True).update(
        validity_to=now
    )
    for district_id in district_ids:
        user_district_class.objects.update_or_create(
            user=i_user,
            location_id=district_id,
            defaults={"validity_to": None, "audit_user_id": audit_user_id},
        )
    cache.delete("q_allowed_locations_" + str(i_user.id))


def create_or_update_officer_villages(officer, village_ids, audit_user_id):
    # To avoid a static dependency from Core to Location, we'll dynamically load this class
    officer_village_class = apps.get_model("location", "OfficerVillage")
    import datetime

    now = datetime.datetime.now()
    officer_village_class.objects.filter(
        officer=officer, validity_to__isnull=True
    ).update(validity_to=now)
    for village_id in village_ids:
        officer_village_class.objects.update_or_create(
            officer=officer,
            location_id=village_id,
            defaults={"validity_to": None, "audit_user_id": audit_user_id},
        )


@validate_payload_for_obligatory_fields(CoreConfig.fields_controls_eo, "data")
def create_or_update_officer(user_id, data, audit_user_id, connected):
    officer_fields = {
        "username": "code",
        "other_names": "other_names",
        "last_name": "last_name",
        "phone": "phone",
        "email": "email",
        "birth_date": "dob",
        "address": "address",
        "works_to": "works_to",
        "location_id": "location_id",
        # TODO veo_code, last_name, other_names, dob, phone
        "substitution_officer_id": "substitution_officer_id",
        "phone_communication": "phone_communication",
    }
    data_subset = {v: data.get(k) for k, v in officer_fields.items()}
    data_subset["audit_user_id"] = audit_user_id
    data_subset["has_login"] = connected
    if user_id:
        # TODO we might want to update a user that has been deleted. Use Legacy ID ?
        officer = Officer.objects.filter(
            validity_to__isnull=True, user__id=user_id
        ).first()
        if officer is not None and officer.validity_to is not None:
            raise ValidationError(_("core.user.edit_historical_data_error"))
    else:
        officer = Officer.objects.filter(
            code=data_subset["code"], validity_to__isnull=True
        ).first()

    if officer:
        officer.save_history()
        [setattr(officer, k, v) for k, v in data_subset.items()]
        created = False
    else:
        officer = Officer(**data_subset)
        created = True

    officer.save()
    if data.get("village_ids"):
        create_or_update_officer_villages(
            officer, data["village_ids"], data_subset["audit_user_id"]
        )
    return officer, created


def create_or_update_claim_admin(user_id, data, audit_user_id, connected):
    ca_fields = {
        "username": "code",
        "other_names": "other_names",
        "last_name": "last_name",
        "phone": "phone",
        "email": "email_id",
        "birth_date": "dob",
        "health_facility_id": "health_facility_id",
    }
    data_subset = {v: data.get(k) for k, v in ca_fields.items()}
    data_subset["audit_user_id"] = audit_user_id
    data_subset["has_login"] = connected
    # Since ClaimAdmin is not in the core module, we have to dynamically load it.
    # If the Claim module is not loaded and someone requests a ClaimAdmin, this will raise an Exception
    claim_admin_class = apps.get_model("core", "ClaimAdmin")
    if user_id:
        # TODO we might want to update a user that has been deleted. Use Legacy ID ?
        claim_admin = claim_admin_class.objects.filter(
            validity_to__isnull=True, user__id=user_id
        ).first()
        if claim_admin is not None and claim_admin.validity_to is not None:
            raise ValidationError(_("core.user.edit_historical_data_error"))
    else:
        claim_admin = claim_admin_class.objects.filter(
            code=data_subset["code"], validity_to__isnull=True
        ).first()

    if claim_admin:
        claim_admin.save_history()
        [setattr(claim_admin, k, v) for k, v in data_subset.items()]
        created = False
    else:
        claim_admin = claim_admin_class(**data_subset)
        created = True

    # TODO update municipalities, regions
    claim_admin.save()
    return claim_admin, created


def create_or_update_core_user(
    user_uuid, username, i_user=None, t_user=None, officer=None, claim_admin=None, user=None
):
    if user_uuid:
        # This intentionally fails if the provided uuid doesn't exist as we don't want clients to set it
        user = User.objects.get(id=user_uuid)
        # There is no history to save for User
        created = False
    elif username:
        user = User.objects.filter(username=username).first()
        created = False
    else:
        user = None
        created = False
    if not user:
        user = User(username=username)
        created = True
    if username:
        user.username = username
    if i_user:
        user.i_user = i_user
    if t_user:
        user.t_user = t_user
    if officer:
        user.officer = officer
    if claim_admin:
        user.claim_admin = claim_admin
    if user.is_dirty(check_relationship=True):
        user.save()
    return user, created


def change_user_password(
    logged_user, username_to_update=None, old_password=None, new_password=None
):
    if username_to_update and username_to_update != logged_user.username:
        if not logged_user.has_perms(CoreConfig.gql_mutation_update_users_perms):
            raise PermissionDenied("unauthorized")
        user_to_update = User.objects.get(username=username_to_update)
    else:
        user_to_update = logged_user
        old_password_match = old_password and user_to_update.check_password(
            old_password
        )
        if not (
            old_password_match
            or user_to_update.stored_password == CoreConfig.locked_user_password_hash
        ):
            raise ValidationError(_("core.wrong_old_password"))

    user_to_update.set_password(new_password)
    user_to_update.save()


### def set_user_password(request, username, token, password):
#  user = User.objects.get(username=username)
#   if default_token_generator.check_token(user, token):
#        user.set_password(password)
#        user.save()
#    else:
#        raise ValidationError("Invalid Token")

def set_user_password(request, username, token, password):
    with transaction.atomic():
        user = User.objects.select_for_update().get(
            username__iexact=username.strip()
        )

        if not default_token_generator.check_token(user, token):
            raise ValidationError("Invalid or expired token")

        user.set_password(password)
        user.save()
        user.clear_refresh_tokens()


def _clear_jwt_cookies(request):
    if hasattr(request, "COOKIES") and isinstance(request.COOKIES, dict):
        request.COOKIES.pop("JWT", None)
        request.COOKIES.pop("JWT-refresh-token", None)


def _try_auto_provision(username, password):
    user, provisioned = UserManager().auto_provision_user(username=username)
    if provisioned:
        logger.debug(f"User {username} was automatically provisioned")
    if user and user.i_user.check_password(password):
        return user
    return None


def user_authentication(request, username, password, allow_expired=False):
    if not username or not password:
        raise exceptions.ParseError(_("Missing username or password"))

    _clear_jwt_cookies(request)

    user = authenticate(request, username=username, password=password)
    if user:
        if user.i_user and user.i_user.is_password_expired:
            if allow_expired:
                return user
            raise exceptions.AuthenticationFailed("PASSWORD_EXPIRED")
        return user

    if not User.objects.filter(username__iexact=username).exists():
        user = _try_auto_provision(username, password)
        if user:
            if user.i_user and user.i_user.is_password_expired:
                if allow_expired:
                    return user
                raise exceptions.AuthenticationFailed("PASSWORD_EXPIRED")
            return user

    logger.debug(f"Authentication failed for username: {username}")
    raise exceptions.AuthenticationFailed("INCORRECT_CREDENTIALS")


def check_user_unique_email(user_email):
    if InteractiveUser.objects.filter(
        email=user_email, validity_to__isnull=True
    ).exists():
        return [{"message": "User email %s already exists" % user_email}]
    return []

#### - Incremental counter function for rate limiting password reset requests
def _increment_reset_counter(key, timeout):
    if cache.add(key, 1, timeout=timeout):
        return 1

    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return 1


def is_password_reset_rate_limited(request, username):
    window = settings.PASSWORD_RESET_RATE_LIMIT_WINDOW
    ip_address = (
        getattr(request, "axes_ip_address", None)
        or request.META.get("REMOTE_ADDR", "unknown")
    )

    normalized_username = (username or "").strip().lower()
    account_hash = hashlib.sha256(
        normalized_username.encode("utf-8")
    ).hexdigest()

    ip_count = _increment_reset_counter(
        f"password-reset:ip:{ip_address}",
        window,
    )
    account_count = _increment_reset_counter(
        f"password-reset:account:{account_hash}",
        window,
    )

    return (
        ip_count > settings.PASSWORD_RESET_RATE_LIMIT_PER_IP
        or account_count > settings.PASSWORD_RESET_RATE_LIMIT_PER_ACCOUNT
    )

## -

def reset_user_password(request, username):
    normalized_username = (username or "").strip()

    user = User.objects.filter(
        Q(username__iexact=normalized_username)
        | Q(i_user__email__iexact=normalized_username),
        *User.filter_validity(),
        *InteractiveUser.filter_validity(prefix="i_user__"),
    ).first()

    if not user:
        logger.info("Password reset requested for an unknown account")
        return False

    if not user.email:
        logger.warning(
            "Password reset requested for user without email; user_id=%s",
            user.pk,
        )
        return False

    token = default_token_generator.make_token(user)
    params = urlencode({
        "token": token,
        "username": user.username,
    })
    reset_url = f"{settings.FRONTEND_URL}/set_password?{params}"

    message = loader.render_to_string(
        CoreConfig.password_reset_template,
        {
            "reset_url": reset_url,
            "user": user,
        },
    )
    escaped_username = escape(user.username)
    escaped_reset_url = escape(reset_url)
    html_message = f"""
        <p>Hello {escaped_username},</p>
        <p>You've recently requested a new password.</p>
        <p>
            <a href="{escaped_reset_url}">Click here to set a new password</a>
        </p>
        <p>Or copy and paste this link into your browser:</p>
        <p><a href="{escaped_reset_url}">{escaped_reset_url}</a></p>
        <p>This link will expire in one hour and can only be used once.</p>
        <p>If you did not request a password reset, you can ignore this email. Your password has not been changed.</p>
        <p>Regards,</p>
    """

    send_result = send_mail(
        subject="[CoreMIS] Reset Password",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
        html_message=html_message,
    )

    logger.warning(
        "Password reset email accepted by email backend; user_id=%s recipient=%s",
        user.pk,
        user.email,
    )

    return send_result > 0
