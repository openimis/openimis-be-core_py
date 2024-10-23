import datetime
import json
import os

from django.db.models import Count, F, Manager, Q, QuerySet
from django.db.models.functions import Coalesce

from core.models import Officer
from location.models import HealthFacility, Location, UserDistrict
from medical_pricelist.models import (
    ItemsPricelist,
    ItemsPricelistDetail,
    ServicesPricelist,
    ServicesPricelistDetail,
)
from payer.models import Payer
from product.models import Product

dir_path = os.path.dirname(os.path.realpath(__file__))

with open(
    os.path.join(dir_path, "../templates/report_status_register.json"), "r"
) as file:
    template = json.load(file)

ALL_REGIONS = -42
ALL_DISTRICTS = -4242

CATEGORY_ACTIVE_EO = "active_eo"
CATEGORY_INACTIVE_EO = "inactive_eo"
CATEGORY_USERS = "users"
CATEGORY_PRODUCTS = "products"
CATEGORY_HFS = "hfs"
CATEGORY_SERVICE_PLS = "service_pls"
CATEGORY_ITEM_PLS = "item_pls"
CATEGORY_SERVICE_PL_DETAILS = "service_pl_details"
CATEGORY_ITEM_PL_DETAILS = "item_pl_details"
CATEGORY_PAYERS = "payers"

UNKNOWN_LOCATION_CODE = "XXXX"
REGION_OTHER_NAME = "Others"
DISTRICT_NATIONAL_NAME = "National - No location specified"
DISTRICT_REGIONAL_NAME = "Regional - No specific district"
DISTRICT_ARCHIVED_NAME = "Error - Archived location"
FAKE_REGION_ID = 0
FAKE_LOCATION_ID = FAKE_REGION_ID
FAKE_ARCHIVED_ID = -1

LOCATION_TYPE_REGION = "R"
LOCATION_TYPE_DISTRICT = "D"


def generate_subtotals_dict():
    """
    Generates a dictionary that represents a subtotal.

    Each key is a category and its corresponding value is the total for this category.


    Returns
    ----------
    dict
        A dictionary that represents a subtotal.
    """
    return {
        CATEGORY_ACTIVE_EO: 0,
        CATEGORY_INACTIVE_EO: 0,
        CATEGORY_USERS: 0,
        CATEGORY_PRODUCTS: 0,
        CATEGORY_HFS: 0,
        CATEGORY_SERVICE_PLS: 0,
        CATEGORY_ITEM_PLS: 0,
        CATEGORY_SERVICE_PL_DETAILS: 0,
        CATEGORY_ITEM_PL_DETAILS: 0,
        CATEGORY_PAYERS: 0,
    }


def dispatch_results(data: dict, category: str, totals: dict, location_mapping: dict):
    """
    Adds the results of a search into the totals.

    Data is dispatched at the location level, at the region level and at the global level.
    """
    for element in data:
        if element["count"]:  # There might not be any record for a given location
            location_id = (
                element["location"] if element["location"] else FAKE_LOCATION_ID
            )  # National data is going to be None
            totals["global"][category] += element["count"]

            if (location_id in location_mapping) or (
                location_id == FAKE_LOCATION_ID
            ):  # = it's a known, active location
                totals["by_location"][location_id][category] += element["count"]

                # Handling regional level data is trickier because national-level data has no location defined
                if not location_id:
                    region_id = FAKE_REGION_ID  # No specific region
                elif location_mapping[location_id]["type"] == LOCATION_TYPE_REGION:
                    region_id = location_id
                else:
                    region_id = location_mapping[location_id]["parent_id"]
                totals["by_region"][region_id][category] += element["count"]
            else:  # Inactive, archived location
                totals["by_location"][FAKE_ARCHIVED_ID][category] += element["count"]
                totals["by_region"][FAKE_REGION_ID][category] += element["count"]


def format_global_totals(report_data: dict, totals: dict):
    """
    Formats the data related to global totals and adds it to the report_data level, with a prefix.
    """
    for key, value in totals["global"].items():
        key_name = f"total_{key}"
        report_data[key_name] = value


def format_final_data(totals: dict, location_mapping: dict):
    # Format the final data to match the expected format
    data = []
    for location_id, location_totals in totals["by_location"].items():
        new_data_line = {**location_totals}
        region_id = find_region_id(location_id, location_mapping)
        add_regional_totals(new_data_line, region_id, totals)
        add_region_district_labels(
            location_id, region_id, new_data_line, location_mapping
        )
        data.append(new_data_line)
    # order results by region, then district
    data.sort(key=lambda x: (x["region_code"], x["district_code"]))
    return data


def find_region_id(location_id: int, location_mapping: dict):
    if location_id < 1:  # It's not a real location, see generate_other_subtotals
        return FAKE_REGION_ID
    location = location_mapping[location_id]
    if location["type"] == LOCATION_TYPE_REGION:
        return location_id
    return location["parent_id"]


def add_regional_totals(new_line: dict, region_id: int, totals: dict):
    # Adds the regional totals to each entry, with a specific "r_" prefix for the region
    for key, value in totals["by_region"][region_id].items():
        new_key = f"r_{key}"
        new_line[new_key] = value


def add_region_district_labels(
    location_id: int, region_id: int, new_data_line: dict, location_mapping: dict
):
    if region_id not in location_mapping:
        new_data_line["region_name"] = REGION_OTHER_NAME
        new_data_line["region_code"] = UNKNOWN_LOCATION_CODE
        new_data_line["district_name"] = (
            DISTRICT_NATIONAL_NAME
            if location_id == FAKE_LOCATION_ID
            else DISTRICT_ARCHIVED_NAME
        )
        new_data_line["district_code"] = UNKNOWN_LOCATION_CODE
    else:
        if location_id == region_id:
            new_data_line["region_name"] = location_mapping[location_id]["name"]
            new_data_line["region_code"] = location_mapping[location_id]["code"]
            new_data_line["district_name"] = DISTRICT_REGIONAL_NAME
            new_data_line["district_code"] = UNKNOWN_LOCATION_CODE
        else:
            new_data_line["region_name"] = location_mapping[region_id]["name"]
            new_data_line["region_code"] = location_mapping[region_id]["code"]
            new_data_line["district_name"] = location_mapping[location_id]["name"]
            new_data_line["district_code"] = location_mapping[location_id]["code"]


def generate_other_subtotals(totals):
    # Prepares fake locations/regions in the totals dictionary for other cases
    totals["by_region"][
        FAKE_REGION_ID
    ] = generate_subtotals_dict()  # Fake region for all special cases
    totals["by_location"][
        FAKE_LOCATION_ID
    ] = (
        generate_subtotals_dict()
    )  # Fake location for national data (no location selected)
    totals["by_location"][
        FAKE_ARCHIVED_ID
    ] = (
        generate_subtotals_dict()
    )  # Fake location for erroneous data (archived location selected)


def fetch_users(location_ids_mapping: dict, search_filters: Q, totals: dict):
    users = fetch_aggregated_data_count(UserDistrict.objects, search_filters)
    dispatch_results(users, CATEGORY_USERS, totals, location_ids_mapping)


def fetch_payers(location_ids_mapping: dict, search_filters: Q, totals: dict):
    # can be national (no district, no region)
    payers = fetch_aggregated_data_count(Payer.objects, search_filters)
    dispatch_results(payers, CATEGORY_PAYERS, totals, location_ids_mapping)


def fetch_item_pricelist_details(
    location_ids_mapping: dict, item_details_filters: Q, totals: dict
):
    # can be national (no district, no region)
    item_pl_details = (
        ItemsPricelistDetail.objects.filter(item_details_filters)
        .values(location=F("items_pricelist__location"))
        .annotate(count=Count(Coalesce("location", 0)))
        .order_by()
    )
    dispatch_results(
        item_pl_details, CATEGORY_ITEM_PL_DETAILS, totals, location_ids_mapping
    )


def fetch_service_pricelist_details(
    location_ids_mapping: dict, service_details_filters: Q, totals: dict
):
    # can be national (no district, no region)
    service_pl_details = (
        ServicesPricelistDetail.objects.filter(service_details_filters)
        .values(location=F("services_pricelist__location"))
        .annotate(count=Count(Coalesce("location", 0)))
        .order_by()
    )
    dispatch_results(
        service_pl_details, CATEGORY_SERVICE_PL_DETAILS, totals, location_ids_mapping
    )


def fetch_item_pricelists(location_ids_mapping: dict, search_filters: Q, totals: dict):
    # can be national (no district, no region)
    item_pls = fetch_aggregated_data_count(ItemsPricelist.objects, search_filters)
    dispatch_results(item_pls, CATEGORY_ITEM_PLS, totals, location_ids_mapping)


def fetch_service_pricelists(
    location_ids_mapping: dict, search_filters: Q, totals: dict
):
    # can be national (no district, no region)
    service_pls = fetch_aggregated_data_count(ServicesPricelist.objects, search_filters)
    dispatch_results(service_pls, CATEGORY_SERVICE_PLS, totals, location_ids_mapping)


def fetch_health_facilities(
    location_ids_mapping: dict, search_filters: Q, totals: dict
):
    hfs = fetch_aggregated_data_count(HealthFacility.objects, search_filters)
    dispatch_results(hfs, CATEGORY_HFS, totals, location_ids_mapping)


def fetch_products(location_ids_mapping: dict, search_filters: Q, totals: dict):
    # can be national (no district, no region)
    products = fetch_aggregated_data_count(Product.objects, search_filters)
    dispatch_results(products, CATEGORY_PRODUCTS, totals, location_ids_mapping)


def fetch_inactive_officers(
    location_ids_mapping: dict, search_filters: Q, totals: dict
):
    # can be national (no district)
    today = datetime.date.today()
    inactive_search_filters = search_filters & Q(works_to__lte=today)
    inactive_officers = fetch_aggregated_data_count(
        Officer.objects, inactive_search_filters
    )
    dispatch_results(
        inactive_officers, CATEGORY_INACTIVE_EO, totals, location_ids_mapping
    )


def fetch_active_officers(location_ids_mapping: dict, search_filters: Q, totals: dict):
    # can be national (no district)
    today = datetime.date.today()
    active_search_filters = search_filters & (
        Q(works_to__isnull=True) | Q(works_to__gt=today)
    )
    active_officers = fetch_aggregated_data_count(
        Officer.objects, active_search_filters
    )
    dispatch_results(active_officers, CATEGORY_ACTIVE_EO, totals, location_ids_mapping)


def fetch_aggregated_data_count(manager: Manager, search_filters: Q):
    # The Count(Coalesce()) allows to group and count NULL values
    return (
        manager.filter(search_filters)
        .values("location")
        .annotate(count=Count(Coalesce("location", 0)))
        .order_by()
    )


def prepare_totals_and_locations(
    active_locations: QuerySet,
    location_ids_mapping: dict,
    totals: dict,
    region_id: int,
    district_id: int,
):
    # Prepares the totals dictionary and adds each location to the mapping
    for location in active_locations:
        location_ids_mapping[location["id"]] = location
        if (
            location["type"] != LOCATION_TYPE_REGION or district_id == ALL_DISTRICTS
        ):  # Don't want to add regional data when a district is specified
            totals["by_location"][location["id"]] = generate_subtotals_dict()
        if location["type"] == LOCATION_TYPE_REGION:
            totals["by_region"][location["id"]] = generate_subtotals_dict()
    if district_id == ALL_DISTRICTS and region_id == ALL_REGIONS:
        generate_other_subtotals(totals)


def registers_status_query(
    user,
    requested_region_id: int = ALL_REGIONS,
    requested_district_id: int = ALL_DISTRICTS,
    **kwargs,
):
    """
    Generates data form the registers status report.

    This function can take a region ID and/or a district ID as parameter
    and counts the use of each region/district in the following models:
    - Officer
    - UserDistrict
    - Product
    - HealthFacility
    - ServicePricelist
    - ServicePricelistDetails
    - ItemPricelist
    - ItemPricelistDetails
    - Payer

    Note: if there is set on a national level (no location selected)
    and a district parameter is sent, the national data doesn't show up in the report

    """
    # Checking the parameters received and returning an error if anything is wrong
    region_id = int(requested_region_id)
    if region_id != ALL_REGIONS:
        region = Location.objects.filter(
            validity_to=None, type="R", id=region_id
        ).first()
        if not region:
            return {"error": "Error - the requested region does not exist"}
    district_id = int(requested_district_id)
    if district_id != ALL_DISTRICTS:
        district_filters = Q(validity_to__isnull=True) & Q(type="D") & Q(id=district_id)
        if (
            region_id != ALL_REGIONS
        ):  # The FE pickers allow you to select a district without a region, so additional steps are required
            district_filters &= Q(parent_id=region_id)
        district = Location.objects.filter(district_filters).first()
        if not district:
            return {"error": "Error - the requested district does not exist"}
        if (
            region_id == ALL_REGIONS
        ):  # The FE pickers allow you to select a district without a region, so additional steps are required
            region = district.parent
            region_id = region.id

    # Preparing data for the header table
    header = {
        "region": (
            "All regions"
            if region_id == ALL_REGIONS
            else f"{region.code} - {region.name}"
        ),
        "district": (
            "All districts"
            if district_id == ALL_DISTRICTS
            else f"{district.code} - {district.name}"
        ),
    }
    report_data = {"header": [header]}

    # Preparing filters of making a list of active locations, which will be the base of this report
    active_location_filters = Q(validity_to__isnull=True)
    if district_id != ALL_DISTRICTS:
        active_location_filters &= Q(id=district_id) | Q(id=region_id)
    elif region_id != ALL_REGIONS:
        active_location_filters &= Q(id=region_id) | Q(parent_id=region_id)
    else:
        active_location_filters &= Q(type__in=["R", "D"])

    # Preparing the list of locations & totals
    active_locations = (
        Location.objects.filter(active_location_filters)
        .values("id", "code", "name", "type", "parent_id")
        .order_by("-type", "code")
    )
    location_ids_mapping = {}
    totals = {
        "global": generate_subtotals_dict(),
        "by_region": {},
        "by_location": {},
    }
    prepare_totals_and_locations(
        active_locations, location_ids_mapping, totals, region_id, district_id
    )

    # Prepare the location filters
    search_filters = Q(validity_to__isnull=True)
    if district_id != ALL_DISTRICTS:
        search_filters &= Q(location_id=district_id)
    elif region_id != ALL_REGIONS:
        search_filters &= Q(location__parent_id=region_id) | Q(location_id=region_id)

    # Fetch every data type
    fetch_active_officers(location_ids_mapping, search_filters, totals)
    fetch_inactive_officers(location_ids_mapping, search_filters, totals)
    fetch_users(location_ids_mapping, search_filters, totals)
    fetch_products(location_ids_mapping, search_filters, totals)
    fetch_health_facilities(location_ids_mapping, search_filters, totals)
    fetch_service_pricelists(location_ids_mapping, search_filters, totals)
    fetch_item_pricelists(location_ids_mapping, search_filters, totals)
    fetch_payers(location_ids_mapping, search_filters, totals)

    # Special filter as location is not directly stored in the object
    service_details_filters = Q(validity_to__isnull=True)
    if district_id != ALL_DISTRICTS:
        service_details_filters &= Q(services_pricelist__location_id=district_id)
    elif region_id != ALL_REGIONS:
        service_details_filters &= Q(
            services_pricelist__location__parent_id=region_id
        ) | Q(services_pricelist__location_id=region_id)
    fetch_service_pricelist_details(
        location_ids_mapping, service_details_filters, totals
    )

    # Special filter as location is not directly stored in the object
    item_details_filters = Q(validity_to__isnull=True)
    if district_id != ALL_DISTRICTS:
        item_details_filters &= Q(items_pricelist__location_id=district_id)
    elif region_id != ALL_REGIONS:
        item_details_filters &= Q(items_pricelist__location__parent_id=region_id) | Q(
            items_pricelist__location_id=region_id
        )
    fetch_item_pricelist_details(location_ids_mapping, item_details_filters, totals)

    # Format the fetched data to match what is required in the report
    format_global_totals(report_data, totals)
    report_data["data"] = format_final_data(totals, location_ids_mapping)

    return report_data
