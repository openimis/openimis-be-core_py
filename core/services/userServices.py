import logging
from gettext import gettext as _

from django.apps import apps
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail, BadHeaderError
from django.template import loader
from django.utils.http import urlencode

from core.apps import CoreConfig
from core.models import User, InteractiveUser, Officer, UserRole
from core.validation.obligatoryFieldValidation import validate_payload_for_obligatory_fields

logger = logging.getLogger(__file__)


def create_or_update_interactive_user(user_id, data, audit_user_id, connected):
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
    data_subset["audit_user_id"] = audit_user_id
    data_subset["role_id"] = data["roles"][0]  # The actual roles are stored in their own table
    data_subset["is_associated"] = connected
    if user_id:
        # TODO we might want to update a user that has been deleted. Use Legacy ID ?
        i_user = InteractiveUser.objects.filter(validity_to__isnull=True, user__id=user_id).first()
    else:
        i_user = InteractiveUser.objects.filter(validity_to__isnull=True, login_name=data_subset["login_name"]).first()
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
            i_user.stored_password = "locked"
        created = True

    i_user.save()
    create_or_update_user_roles(i_user, data["roles"], audit_user_id)
    if "districts" in data:
        create_or_update_user_districts(
            i_user, data["districts"], data_subset["audit_user_id"]
        )
    return i_user, created


def create_or_update_user_roles(i_user, role_ids, audit_user_id):
    from core import datetime

    now = datetime.datetime.now()
    UserRole.objects.filter(user=i_user, validity_to__isnull=True).update(
        validity_to=now
    )
    for role_id in role_ids:
        UserRole.objects.create(
            user=i_user, role_id=role_id, audit_user_id=audit_user_id
        )


# TODO move to location module ?
def create_or_update_user_districts(i_user, district_ids, audit_user_id):
    # To avoid a static dependency from Core to Location, we'll dynamically load this class
    user_district_class = apps.get_model("location", "UserDistrict")
    from core import datetime

    now = datetime.datetime.now()
    user_district_class.objects.filter(user=i_user, validity_to__isnull=True).update(
        validity_to=now.to_ad_datetime()
    )
    for district_id in district_ids:
        user_district_class.objects.update_or_create(
            user=i_user,
            location_id=district_id,
            defaults={"validity_to": None, "audit_user_id": audit_user_id},
        )


def create_or_update_officer_villages(officer, village_ids, audit_user_id):
    # To avoid a static dependency from Core to Location, we'll dynamically load this class
    officer_village_class = apps.get_model("location", "OfficerVillage")
    from core import datetime

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


@validate_payload_for_obligatory_fields(CoreConfig.fields_controls_eo, 'data')
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
    claim_admin_class = apps.get_model("claim", "ClaimAdmin")
    if user_id:
        # TODO we might want to update a user that has been deleted. Use Legacy ID ?
        claim_admin = claim_admin_class.objects.filter(validity_to__isnull=True, user__id=user_id).first()
    else:
        claim_admin = claim_admin_class.objects.filter(code=data_subset["code"], validity_to__isnull=True).first()

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


def create_or_update_core_user(user_uuid, username, i_user=None, t_user=None, officer=None, claim_admin=None):
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
    user.save()
    return user, created


def change_user_password(logged_user, username_to_update=None, old_password=None, new_password=None):
    if username_to_update and username_to_update != logged_user.username:
        if not logged_user.has_perms(CoreConfig.gql_mutation_update_users_perms):
            raise PermissionDenied("unauthorized")
        user_to_update = User.objects.get(username=username_to_update)
    else:
        user_to_update = logged_user
        if not old_password or not user_to_update.check_password(old_password):
            raise ValidationError(_("core.wrong_old_password"))

    user_to_update.set_password(new_password)
    user_to_update.save()


def set_user_password(request, username, token, password):
    user = User.objects.get(username=username)

    if default_token_generator.check_token(user, token):
        user.set_password(password)
        user.save()
    else:
        raise ValidationError("Invalid Token")


def check_user_unique_email(user_email):
    if InteractiveUser.objects.filter(email=user_email, validity_to__isnull=True).exists():
        return [{"message": "User email %s already exists" % user_email}]
    return []


def reset_user_password(request, username):
    user = User.objects.get(username=username)
    user.clear_refresh_tokens()

    if not user.email:
        raise ValidationError(
            f"User {username} cannot reset password because he has no email address"
        )

    token = default_token_generator.make_token(user)
    try:
        logger.info(f"Send mail to reset password for {user} with token '{token}'")
        params = urlencode({"token": token})
        reset_url = f"{settings.FRONTEND_URL}/set_password?{params}"
        message = loader.render_to_string(
            CoreConfig.password_reset_template,
            {
                "reset_url": reset_url,
                "user": user,
            },
        )
        logger.debug("Message sent: %s" % message)
        email_to_send = send_mail(
            subject="[OpenIMIS] Reset Password",
            message=message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return email_to_send
    except BadHeaderError:
        return ValueError("Invalid header found.")
