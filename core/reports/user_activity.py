import os
import json
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, Q
from django.db.models.functions import Coalesce

from core.models import InteractiveUser, Officer
from payer.models import Payer

# If manually pasting from reportbro and you have test data, search and replace \" with '

dir_path = os.path.dirname(os.path.realpath(__file__))

with open(os.path.join(dir_path, "../templates/report_user_activity.json"), "r") as file:
    template = json.load(file)


# All constant values used below
ALL_USERS = -42

ACTION_LOGIN = "L"  # Information no longer saved
ACTION_LOGOUT = "O"  # Information no longer saved
ACTION_INSERT = "I"
ACTION_UPDATE = "U"
ACTION_DELETE = "D"
ACTION_ALL = "A"
AVAILABLE_ACTIONS = [ACTION_INSERT, ACTION_UPDATE, ACTION_DELETE]

ENTITY_CLAIM = "Claim"
ENTITY_BATCH_RUN = "BatchRun"
ENTITY_CLAIM_ADMIN = "ClaimAdmin"
ENTITY_LOCATION = "Location"
ENTITY_EXTRACT = "Extract"
ENTITY_FAMILY = "Family"
ENTITY_FEEDBACK = "Feedback"
ENTITY_LOC_HF = "HealthFacility"
ENTITY_INSUREE = "Insuree"
ENTITY_ITEM = "Item"
ENTITY_OFFICER = "Officer"
ENTITY_PAYER = "Payer"
ENTITY_PHOTO = "InsureePhoto"
ENTITY_PL_ITEM = "ItemsPricelist"
ENTITY_PL_SERVICE = "ServicesPricelist"
ENTITY_PL_ITEM_DETAILS = "ItemsPricelistDetail"
ENTITY_PL_SERVICE_DETAILS = "ServicesPricelistDetail"
ENTITY_POLICY = "Policy"
ENTITY_PREMIUM = "Premium"
ENTITY_PRODUCT = "Product"
ENTITY_PRODUCT_ITEM = "ProductItem"
ENTITY_PRODUCT_SERVICE = "ProductService"
ENTITY_RELATIVE_DISTRIBUTION = "RelativeDistribution"
ENTITY_SERVICE = "Service"
ENTITY_USER = "InteractiveUser"
ENTITY_USER_DISTRICT = "UserDistrict"
ENTITY_LOGINS = "ENTITY_LOGINS"  # Information no longer saved
ENTITY_ICD = "ENTITY_ICD"  # Information no longer saved - no user interaction with ICDs
ENTITY_ALL = "ENTITY_ALL"
AVAILABLE_ENTITIES = [
    ENTITY_CLAIM,
    ENTITY_BATCH_RUN,
    ENTITY_CLAIM_ADMIN,
    ENTITY_LOCATION,
    ENTITY_EXTRACT,
    ENTITY_FAMILY,
    ENTITY_FEEDBACK,
    ENTITY_LOC_HF,
    ENTITY_INSUREE,
    ENTITY_ITEM,
    ENTITY_OFFICER,
    ENTITY_PAYER,
    ENTITY_PHOTO,
    ENTITY_PL_ITEM,
    ENTITY_PL_SERVICE,
    ENTITY_PL_ITEM_DETAILS,
    ENTITY_PL_SERVICE_DETAILS,
    ENTITY_POLICY,
    ENTITY_PREMIUM,
    ENTITY_PRODUCT,
    ENTITY_PRODUCT_ITEM,
    ENTITY_PRODUCT_SERVICE,
    ENTITY_RELATIVE_DISTRIBUTION,
    ENTITY_SERVICE,
    ENTITY_USER,
    ENTITY_USER_DISTRICT,
]

# Maps an entity to its module name
MODULE_MAPPING = {
    ENTITY_CLAIM: "claim",
    ENTITY_BATCH_RUN: "claim_batch",
    ENTITY_CLAIM_ADMIN: "claim",
    ENTITY_LOCATION: "location",
    ENTITY_EXTRACT: "tools",
    ENTITY_FAMILY: "insuree",
    ENTITY_FEEDBACK: "claim",
    ENTITY_LOC_HF: "location",
    ENTITY_INSUREE: "insuree",
    ENTITY_ITEM: "medical",
    ENTITY_OFFICER: "core",
    ENTITY_PAYER: "payer",
    ENTITY_PHOTO: "insuree",
    ENTITY_PL_ITEM: "medical_pricelist",
    ENTITY_PL_SERVICE: "medical_pricelist",
    ENTITY_PL_ITEM_DETAILS: "medical_pricelist",
    ENTITY_PL_SERVICE_DETAILS: "medical_pricelist",
    ENTITY_POLICY: "policy",
    ENTITY_PREMIUM: "contribution",
    ENTITY_PRODUCT: "product",
    ENTITY_PRODUCT_ITEM: "product",
    ENTITY_PRODUCT_SERVICE: "product",
    ENTITY_RELATIVE_DISTRIBUTION: "claim_batch",
    ENTITY_SERVICE: "medical",
    ENTITY_USER: "core",
    ENTITY_USER_DISTRICT: "location",
}

# Used for the description
EXTRACT_DIRECTIONS = {
    0: "Export",
    1: "Import",
}

# Used for the description
LOCATION_TYPES = {"R": "Region", "D": "District", "W": "Ward", "V": "Village"}


def determine_action_type(
    element_id: int, validity_to: str, legacy_id: str, known_legacy_ids: set
):
    # Determines whether this is a creation, an update or a suppression
    if legacy_id:
        if legacy_id in known_legacy_ids:
            # New update of a known element
            return ACTION_UPDATE
        else:
            # First occurrence of an element that has been updated since
            known_legacy_ids.add(legacy_id)
            return ACTION_INSERT
    else:
        if validity_to:
            # The only situation that matches [no legacy_id + a validity_to] = deleted element
            return ACTION_DELETE
        else:
            if element_id in known_legacy_ids:
                # It's the latest update of an element that has already been updated
                return ACTION_UPDATE
            else:
                # It's the first occurrence of this element, and it hasn't been updated yet
                return ACTION_INSERT


def determine_description(entity, element):
    # Determines the description string that must be generated, based on the element's nature
    if entity == ENTITY_CLAIM:
        hf_code = element.health_facility.code
        return f"Claim {element.code} for Health Facility {hf_code}"
    if entity == ENTITY_BATCH_RUN:
        location = element.location
        location_string = (
            f"{location.name} ({location.code})"
            if location
            else "all regions & districts"
        )
        return f"Batch run for period {element.run_month}/{element.run_year} in {location_string}"
    if entity == ENTITY_CLAIM_ADMIN:
        return f"Claim admin {element.code} - {element.other_names} {element.last_name}"
    if entity == ENTITY_EXTRACT:
        direction = EXTRACT_DIRECTIONS.get(element.direction, "Unknown")
        return f"Extract done on {element.date} - {direction} - {element.type}"
    if entity == ENTITY_FAMILY:
        location = element.location
        location_string = (
            f"{location.name} ({location.code})" if location else "without any location"
        )
        return f"Family - Head number {element.head_insuree.chf_id} - {location_string}"
    if entity == ENTITY_FEEDBACK:
        officer = Officer.objects.filter(id=element.officer_id).first()
        officer_name = (
            f"{officer.other_names} {officer.last_name}"
            if officer
            else "unknown Officer"
        )
        claim_name = f"Claim {element.claim.code}" if element.claim else "unknown Claim"
        return f"Feedback entered on {element.feedback_date} by {officer_name} for {claim_name}"
    if entity == ENTITY_LOC_HF:
        return f"Health Facility {element.code} - {element.name} in {element.location.name} ({element.location.code})"
    if entity == ENTITY_INSUREE:
        return f"Insuree {element.chf_id} - {element.other_names} {element.last_name}"
    if entity == ENTITY_ITEM:
        return f"Item {element.code} - {element.name}"
    if entity == ENTITY_OFFICER:
        return f"Enrollment Officer {element.code} - {element.other_names} {element.last_name}"
    if entity == ENTITY_PAYER:
        displayed_type = "Unknown"
        for payer_type in Payer.PAYER_TYPE_CHOICES:
            if payer_type[0] == element.type:
                displayed_type = payer_type[1]
                break
        return f"Payer {element.name} - type {displayed_type}"
    if entity == ENTITY_PHOTO:
        return f"Insuree Picture for Insuree {element.insuree.chf_id}"
    if entity == ENTITY_PL_ITEM:
        location = element.location
        location_string = (
            f"{location.name} ({location.code})"
            if location
            else "without specific location"
        )
        return f"Item Pricelist - {element.name} - {location_string}"
    if entity == ENTITY_PL_SERVICE:
        location = element.location
        location_string = (
            f"{location.name} ({location.code})"
            if location
            else "without specific location"
        )
        return f"Service Pricelist - {element.name} - {location_string}"
    if entity == ENTITY_PL_ITEM_DETAILS:
        return f'Item {element.item.code} - {element.item.name} - in the Price List "{element.items_pricelist.name}"'
    if entity == ENTITY_PL_SERVICE_DETAILS:
        return f'Service {element.service.code} - {element.service.name}\
- in the Price List "{element.services_pricelist.name}"'
    if entity == ENTITY_POLICY:
        return f"Policy to Family - Head number {element.family.head_insuree.chf_id}"
    if entity == ENTITY_PREMIUM:
        return f"Premium of {element.amount}\
- Family Head {element.policy.family.head_insuree.chf_id}\
- Policy start on {element.policy.start_date}"
    if entity == ENTITY_PRODUCT:
        return f"Product {element.code} - {element.name}"
    if entity == ENTITY_PRODUCT_ITEM:
        return f"Item {element.item.code} in Product {element.product.code}"
    if entity == ENTITY_PRODUCT_SERVICE:
        return f"Service {element.service.code} in Product {element.product.code}"
    if entity == ENTITY_RELATIVE_DISTRIBUTION:
        return f"Relative distribution in Product {element.product.code} - {element.product.name}"
    if entity == ENTITY_SERVICE:
        return f"Service {element.code} - {element.name}"
    if entity == ENTITY_USER:
        return f"User {element.other_names} {element.last_name} - login {element.login_name}"
    if entity == ENTITY_USER_DISTRICT:
        return f"User {element.user.login_name} assigned to District {element.location.code} {element.location.name}"
    if entity == ENTITY_LOCATION:
        return f"{LOCATION_TYPES[element.type]} {element.code} - {element.name} "
    else:
        # This should not happen, but just in case
        return f"{element.id} - {element.legacy_id} - from {element.validity_from} - to {element.validity_to}"


def determine_datetime(validity_to, validity_from, action_type):
    # Determines which date must be used
    if action_type == ACTION_INSERT:
        return validity_from
    return validity_to if validity_to else validity_from


def fetch_entity_data(
    requested_entity: str,
    report_params: dict,
    user_id: int,
    user_names_mapping: dict,
    trigger_missing_entity_error=True,
):
    data = []
    try:
        manager = apps.get_model(MODULE_MAPPING[requested_entity], requested_entity)
        # TODO : prepare a mapping of the list of fields that are needed for each entity -> use .only(list) ?
        filters = (
            Q(validity_to__lte=report_params["date_to"])
            & Q(validity_to__gte=report_params["date_from"])
        ) | (
            Q(validity_to__isnull=True)
            & Q(validity_from__lte=report_params["date_to"])
            & Q(validity_from__gte=report_params["date_from"])
        )
        if user_id != ALL_USERS:
            filters &= Q(audit_user_id=user_id)
        elements = (
            manager.objects.filter(filters)
            .annotate(order_date=Coalesce("validity_to", "validity_from"))
            .order_by("order_date", "-id")
        )

        known_legacy_ids = set()

        for element in elements:

            action_type = determine_action_type(
                element.id, element.validity_to, element.legacy_id, known_legacy_ids
            )
            if (
                action_type != report_params["action"]
                and report_params["action"] != ACTION_ALL
            ):
                continue

            new_data_element = {
                "entity": requested_entity,
                "action": action_type,
                "description": determine_description(requested_entity, element),
                "datetime": determine_datetime(
                    element.validity_to, element.validity_from, action_type
                ),
                "user_name": user_names_mapping.get(element.audit_user_id, "openIMIS"),
            }
            data.append(new_data_element)

        return True, data

    except LookupError:
        if trigger_missing_entity_error:
            return False, data


def map_user_ids_to_user_names():
    mapping = {}
    users = InteractiveUser.objects.order_by("id").all()
    for user in users:
        mapping[user.id] = f"{user.other_names} {user.last_name}"
    return mapping


def user_activity_query(
    user,
    date_start: str,
    date_end: str,
    requested_user_id: int = ALL_USERS,
    action: str = ACTION_ALL,
    entity: str = ENTITY_ALL,
    **kwargs,
):
    # Checking the parameters received and returning an error if anything is wrong
    if entity != ENTITY_ALL and entity not in AVAILABLE_ENTITIES:
        return {"error": "Error - entity requested not available"}
    if action != ACTION_ALL and action not in AVAILABLE_ACTIONS:
        return {"error": "Error - action requested not available"}
    if date_start > date_end:
        return {"error": "Error - the start date cannot be greater than the end date"}
    user_id = int(requested_user_id)
    if user_id != ALL_USERS:
        try:
            user = InteractiveUser.objects.get(id=user_id)
        except ObjectDoesNotExist:
            return {"error": "Error - the user requested does not exist"}

    # Preparing data for the header table
    header = {
        "user_name": (
            f"{user.other_names} {user.last_name}"
            if user_id != ALL_USERS
            else "All users"
        ),
        "date_from": date_start,
        "date_to": date_end,
        "entity": entity,
        "action": action,
    }
    report_data = {"header": [header]}

    # Fetching all usernames in order to display them
    user_names_mapping = map_user_ids_to_user_names()

    # Fetching data for a single entity
    if entity != ENTITY_ALL:
        fetch_success, entity_data = fetch_entity_data(
            entity, header, user_id, user_names_mapping
        )

        if fetch_success:
            entity_data.sort(key=lambda x: (x["user_name"], x["datetime"]))
            report_data["data"] = entity_data
        else:
            report_data["error"] = "Error - the module requested is not installed"

        return report_data

    else:
        # Fetching data for all available entities that are installed in the current instance
        fetched_data = []
        for current_entity in AVAILABLE_ENTITIES:
            fetch_success, entity_data = fetch_entity_data(
                current_entity,
                header,
                user_id,
                user_names_mapping,
                trigger_missing_entity_error=False,
            )
            fetched_data.extend(entity_data)

        fetched_data.sort(key=lambda x: (x["user_name"], x["datetime"]))
        report_data["data"] = fetched_data

        return report_data
