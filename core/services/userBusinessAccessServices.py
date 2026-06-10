import datetime
import logging

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q

from core.models import UserBusinessAccess

logger = logging.getLogger(__name__)

LINK_TYPE_CA = "ca"
LINK_TYPE_EO = "eo"


def _content_type_for_model(model):
    return ContentType.objects.get_for_model(model)


def _object_access_key(object_id):
    return str(object_id)


def _valid_business_access_queryset(queryset=None, validity=None):
    queryset = queryset if queryset is not None else UserBusinessAccess.objects.all()
    return queryset.filter(**UserBusinessAccess.filter_validity(validity=validity)).filter(
        UserBusinessAccess.filter_validity_q(validity=validity)
    )


def _apply_user_profile_search(queryset, search):
    if not search:
        return queryset
    return queryset.filter(
        Q(username__icontains=search)
        | Q(i_user__last_name__icontains=search)
        | Q(i_user__other_names__icontains=search)
    )


def _profile_fields_from_user(user):
    i_user = getattr(user, "i_user", None)
    return {
        "code": user.username,
        "last_name": i_user.last_name if i_user else "",
        "other_names": i_user.other_names if i_user else "",
        "email": i_user.email if i_user else None,
        "phone": i_user.phone if i_user else None,
    }


def _officer_from_user(user):
    Officer = apps.get_model("core", "Officer")
    fields = _profile_fields_from_user(user)
    return Officer(
        id=user.id,
        uuid=str(user.uuid),
        code=fields["code"],
        last_name=fields["last_name"],
        other_names=fields["other_names"],
        email=fields["email"],
        phone=fields["phone"],
        audit_user_id=-1,
    )


def _claim_admin_from_user(user, health_facility=None):
    ClaimAdmin = apps.get_model("core", "ClaimAdmin")
    fields = _profile_fields_from_user(user)
    claim_admin = ClaimAdmin(
        id=user.id,
        uuid=str(user.uuid),
        code=fields["code"],
        last_name=fields["last_name"],
        other_names=fields["other_names"],
        email_id=fields["email"],
        phone=fields["phone"],
        audit_user_id=-1,
    )
    if health_facility is not None:
        claim_admin.health_facility = health_facility
        claim_admin.health_facility_id = health_facility.id
    return claim_admin


def _matches_officer_search(officer, search):
    if not search:
        return True
    search = search.lower()
    return any(
        value and value.lower().startswith(search)
        for value in (
            officer.code,
            officer.last_name,
            officer.other_names,
            officer.email,
        )
    )


def get_user_ids_by_link_type(link_type, validity=None):
    return (
        _valid_business_access_queryset(
            UserBusinessAccess.objects.filter(link_type=link_type),
            validity=validity,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )


def _user_health_facility_map(user_ids, link_type=LINK_TYPE_CA):
    HealthFacility = apps.get_model("location", "HealthFacility")
    accesses = _valid_business_access_queryset(
        UserBusinessAccess.objects.filter(
            user_id__in=user_ids,
            link_type=link_type,
            content_type=_content_type_for_model(HealthFacility),
        )
    )
    hf_uuids = {str(object_id) for object_id in accesses.values_list("object_id", flat=True)}
    health_facilities = {
        str(health_facility.uuid): health_facility
        for health_facility in HealthFacility.objects.filter(uuid__in=hf_uuids)
    }
    user_health_facility = {}
    for access in accesses:
        health_facility = health_facilities.get(str(access.object_id))
        if health_facility and access.user_id not in user_health_facility:
            user_health_facility[access.user_id] = health_facility
    return user_health_facility


def get_business_access_queryset(link_type, model, object_uuids=None, validity=None):
    content_type = _content_type_for_model(model)
    accesses = _valid_business_access_queryset(
        UserBusinessAccess.objects.filter(
            link_type=link_type,
            content_type=content_type,
        ),
        validity=validity,
    )

    if object_uuids is not None:
        object_uuids = [str(object_uuid) for object_uuid in object_uuids if object_uuid]
        if not object_uuids:
            return accesses.none()
        accesses = accesses.filter(object_id__in=object_uuids)

    return accesses


def get_business_access_user_ids(link_type, model, object_uuids=None, validity=None):
    return (
        get_business_access_queryset(link_type, model, object_uuids, validity=validity)
        .values_list("user_id", flat=True)
        .distinct()
    )

def _audit_user_for_save(audit_user):
    if audit_user in (None, -1):
        return None
    if isinstance(audit_user, int):
        User = apps.get_model("core", "User")
        return User.objects.filter(id=audit_user).first()
    return audit_user


def sync_user_business_accesses(core_user, link_type, content_type, object_ids, audit_user=None):
    """
    Reconcile UserBusinessAccess rows for a user/link_type.
    Used by user mutations and one-off legacy data migrations.
    """
    if not core_user or not object_ids or not link_type:
        return

    object_ids = {str(object_id) for object_id in object_ids if object_id}
    if not object_ids:
        return

    now = datetime.datetime.now()
    save_user = _audit_user_for_save(audit_user) or core_user
    existing = _valid_business_access_queryset(
        UserBusinessAccess.objects.filter(
            user=core_user,
            link_type=link_type,
        ),
        validity=now,
    )

    existing_keys = {
        _object_access_key(access.object_id): access for access in existing
    }
    desired_keys = {
        _object_access_key(object_id): object_id for object_id in object_ids
    }

    for key, access in existing_keys.items():
        if key not in desired_keys:
            access.active = False
            access.date_valid_to = now
            access.save(user=save_user)

    for object_id in object_ids:
        key = _object_access_key(object_id)
        if key in existing_keys:
            continue
        access = UserBusinessAccess(
            user=core_user,
            link_type=link_type,
            content_type=content_type,
            object_id=object_id,
            date_valid_from=now,
            date_valid_to=None,
            active=True,
        )
        access.save(user=save_user)


def deactivate_user_business_accesses(core_user, link_type, audit_user=None):
    if not core_user or not link_type:
        return

    now = datetime.datetime.now()
    save_user = _audit_user_for_save(audit_user) or core_user
    accesses = _valid_business_access_queryset(
        UserBusinessAccess.objects.filter(
            user=core_user,
            link_type=link_type,
        ),
        validity=now,
    )

    for access in accesses:
        access.active = False
        access.date_valid_to = now
        access.save(user=save_user)


def apply_claim_admin_business_access(core_user, health_facility_id, audit_user=None):
    """Set claim-admin business access for a user (user mutation path)."""
    HealthFacility = apps.get_model("location", "HealthFacility")
    health_facility = HealthFacility.objects.filter(id=health_facility_id).first()
    if not health_facility:
        logger.warning(
            "Cannot apply claim admin business access: health facility %s not found",
            health_facility_id,
        )
        return

    content_type = _content_type_for_model(HealthFacility)
    sync_user_business_accesses(
        core_user,
        LINK_TYPE_CA,
        content_type,
        [health_facility.uuid],
        audit_user,
    )


def apply_officer_business_accesses(core_user, village_ids, audit_user=None):
    """Set enrolment-officer business access for a user (user mutation path)."""
    Location = apps.get_model("location", "Location")
    villages = Location.objects.filter(id__in=village_ids)
    if not villages.exists():
        logger.warning(
            "Cannot apply officer business access: no villages found for ids %s",
            village_ids,
        )
        return

    content_type = _content_type_for_model(Location)
    sync_user_business_accesses(
        core_user,
        LINK_TYPE_EO,
        content_type,
        villages.values_list("uuid", flat=True),
        audit_user,
    )


def clear_claim_admin_business_access(core_user, audit_user=None):
    deactivate_user_business_accesses(core_user, LINK_TYPE_CA, audit_user=audit_user)


def clear_officer_business_accesses(core_user, audit_user=None):
    deactivate_user_business_accesses(core_user, LINK_TYPE_EO, audit_user=audit_user)


def _allowed_health_facility_uuids(user, district_uuid=None, region_uuid=None, **kwargs):
    HealthFacility = apps.get_model("location", "HealthFacility")
    hf_queryset = HealthFacility.get_queryset(None, user, **kwargs)
    hf_queryset = HealthFacility.filter_queryset(hf_queryset)
    if district_uuid is not None:
        hf_queryset = hf_queryset.filter(location__uuid=district_uuid)
    elif region_uuid is not None:
        hf_queryset = hf_queryset.filter(location__parent__uuid=region_uuid)
    return list(hf_queryset.values_list("uuid", flat=True))


def _allowed_location_uuids(user, **kwargs):
    Location = apps.get_model("location", "Location")
    location_queryset = Location.get_queryset(None, user)
    location_queryset = Location.filter_queryset(location_queryset)
    return list(location_queryset.values_list("uuid", flat=True))


def get_claim_admins_for_user(
    user, search=None, district_uuid=None, region_uuid=None, **kwargs
):
    hf_uuids = _allowed_health_facility_uuids(
        user,
        district_uuid=district_uuid,
        region_uuid=region_uuid,
        **kwargs,
    )
    if not hf_uuids:
        return []
    return get_claim_admins_from_business_access(hf_uuids, search=search)


def get_officers_for_user(user, search=None, **kwargs):
    location_uuids = _allowed_location_uuids(user, **kwargs)
    if not location_uuids:
        return []
    return get_officers_from_business_access(location_uuids, search=search)


def get_claim_admins_from_business_access(object_uuids=None, search=None):
    HealthFacility = apps.get_model("location", "HealthFacility")
    User = apps.get_model("core", "User")

    user_ids = list(
        get_business_access_user_ids(LINK_TYPE_CA, HealthFacility, object_uuids)
    )
    if not user_ids:
        return []

    users = _apply_user_profile_search(
        User.objects.filter(id__in=user_ids).select_related("i_user"),
        search,
    )
    user_health_facility = _user_health_facility_map(user_ids)
    return [
        _claim_admin_from_user(user, user_health_facility.get(user.id))
        for user in users
    ]


def get_officers_from_business_access(object_uuids=None, search=None):
    Location = apps.get_model("location", "Location")
    User = apps.get_model("core", "User")

    user_ids = list(
        get_business_access_user_ids(LINK_TYPE_EO, Location, object_uuids)
    )
    if not user_ids:
        return []

    users = _apply_user_profile_search(
        User.objects.filter(id__in=user_ids).select_related("i_user"),
        search,
    )
    return [_officer_from_user(user) for user in users]


def get_substitution_officers_from_business_access(
    villages_uuids, officer_uuid=None, search=None
):
    Location = apps.get_model("location", "Location")
    User = apps.get_model("core", "User")

    villages_uuids = [str(village_uuid) for village_uuid in (villages_uuids or []) if village_uuid]
    if not villages_uuids:
        return []

    required_villages = len(villages_uuids)
    matching_user_ids = (
        _valid_business_access_queryset(
            UserBusinessAccess.objects.filter(
                link_type=LINK_TYPE_EO,
                content_type=_content_type_for_model(Location),
                object_id__in=villages_uuids,
            )
        )
        .values("user_id")
        .annotate(matched_villages=Count("object_id", distinct=True))
        .filter(matched_villages=required_villages)
        .values_list("user_id", flat=True)
    )

    users = User.objects.filter(id__in=matching_user_ids).select_related("i_user")
    if officer_uuid:
        users = users.exclude(uuid=officer_uuid)

    officers = [_officer_from_user(user) for user in users]
    if search:
        officers = [officer for officer in officers if _matches_officer_search(officer, search)]
    return officers


def migrate_claim_admins_to_business_access(audit_user_id=-1):
    """
    One-off migration helper: copy legacy tblClaimAdmin HF links into UserBusinessAccess.
    """
    User = apps.get_model("core", "User")
    ClaimAdmin = apps.get_model("core", "ClaimAdmin")
    HealthFacility = apps.get_model("location", "HealthFacility")
    content_type = _content_type_for_model(HealthFacility)

    migrated = 0
    for claim_admin in ClaimAdmin.objects.filter(*ClaimAdmin.filter_validity()).select_related(
        "health_facility"
    ):
        if not claim_admin.health_facility_id:
            continue

        user = User.objects.filter(claim_admin_id=claim_admin.id).first()
        if not user and claim_admin.code:
            user = User.objects.filter(username=claim_admin.code).first()
        if not user:
            continue

        sync_user_business_accesses(
            user,
            LINK_TYPE_CA,
            content_type,
            [claim_admin.health_facility.uuid],
            audit_user_id,
        )
        migrated += 1

    logger.info("Migrated %s claim administrators to UserBusinessAccess", migrated)
    return migrated


def migrate_officers_to_business_access(audit_user_id=-1):
    """
    One-off migration helper: copy legacy OfficerVillage links into UserBusinessAccess.
    """
    User = apps.get_model("core", "User")
    Officer = apps.get_model("core", "Officer")
    OfficerVillage = apps.get_model("location", "OfficerVillage")
    content_type = _content_type_for_model(apps.get_model("location", "Location"))

    migrated = 0
    for officer in Officer.objects.filter(*Officer.filter_validity()):
        user = User.objects.filter(officer_id=officer.id).first()
        if not user and officer.code:
            user = User.objects.filter(username=officer.code).first()
        if not user:
            continue

        village_uuids = (
            OfficerVillage.objects.filter(
                officer=officer,
                *OfficerVillage.filter_validity(),
            )
            .select_related("location")
            .values_list("location__uuid", flat=True)
        )
        village_uuids = [uuid for uuid in village_uuids if uuid]
        if not village_uuids:
            continue

        sync_user_business_accesses(
            user,
            LINK_TYPE_EO,
            content_type,
            village_uuids,
            audit_user_id,
        )
        migrated += 1

    logger.info("Migrated %s enrolment officers to UserBusinessAccess", migrated)
    return migrated