import datetime

import factory

from core.models import Role, RoleRight
from core.utils import collect_all_gql_permissions

# HF and Offline administrators intentionally carry the same rights, only the is_system bit differs.
_HF_ADMIN_PERMS = [
    "gql_query_users_perms",
    "gql_mutation_create_users_perms",
    "gql_mutation_update_users_perms",
    "gql_mutation_delete_users_perms",
    "gql_query_health_facilities_perms",
    "gql_mutation_edit_health_facilities_perms",
    "gql_mutation_delete_health_facilities_perms",
    "gql_query_medical_items_perms",
    "gql_mutation_medical_items_update_perms",
    "gql_query_medical_services_perms",
    "gql_mutation_medical_services_update_perms",
    "gql_query_pricelists_medical_items_perms",
    "gql_mutation_pricelists_medical_items_update_perms",
    "gql_mutation_pricelists_medical_items_delete_perms",
    "gql_query_pricelists_medical_services_perms",
    "gql_mutation_pricelists_medical_services_update_perms",
    "gql_mutation_pricelists_medical_services_delete_perms",
    "gql_reports_capitation_payment_perms",
    "gql_reports_user_activity_perms",
    "gql_reports_status_of_register_perms",
    "gql_reports_overview_of_commissions_perms",
]

ROLE_PRESETS = {
    "EnrolmentOfficer": {
        "is_system": 1,
        "perm_names": [
            "gql_query_insuree_perms",
            "gql_mutation_update_insurees_perms",
            "gql_mutation_create_insurees_perms",
            "gql_query_locations_perms",
            "gql_query_products_perms",
            "gql_query_policies_perms",
            "gql_mutation_create_policies_perms",
            "gql_mutation_edit_policies_perms",
        ],
    },
    "Manager": {
        "is_system": 2,
        "perm_names": [
            "gql_reports_primary_operational_indicators_claims_perms",
            "gql_reports_derived_operational_indicators_perms",
            "gql_reports_contribution_collection_perms",
            "gql_reports_user_activity_perms",
            "gql_query_insuree_inquire_perms",
        ],
    },
    "Accountant": {
        "is_system": 4,
        "perm_names": [
            "gql_query_families_perms",
            "gql_query_insurees_perms",
            "gql_query_insuree_inquire_perms",
            "gql_query_policies_perms",
            "gql_query_premiums_perms",
            "gql_query_payments_perms",
            "gql_mutation_create_payments_perms",
            "gql_mutation_update_payments_perms",
            "gql_mutation_delete_payments_perms",
            "gql_query_claims_perms",
            "gql_mutation_create_claims_perms",
            "gql_mutation_update_claims_perms",
            "gql_mutation_delete_claims_perms",
            "gql_reports_contribution_collection_perms",
            "gql_reports_product_sales_perms",
            "gql_reports_contribution_distribution_perms",
            "gql_reports_payment_category_overview_perms",
            "gql_reports_matching_funds_perms",
            "gql_reports_claim_overview_report_perms",
            "gql_reports_percentage_referrals_perms",
            "gql_reports_families_insurees_overview_perms",
            "gql_reports_pending_insurees_perms",
            "gql_reports_renewals_perms",
            "gql_reports_capitation_payment_perms",
            "gql_reports_rejected_photo_perms",
            "gql_reports_contribution_payment_perms",
            "gql_reports_control_number_assignment_perms",
            "gql_reports_overview_of_commissions_perms",
        ],
    },
    "Clerk": {
        "is_system": 8,
        "perm_names": [
            "gql_query_families_perms",
            "gql_mutation_create_families_perms",
            "gql_mutation_update_families_perms",
            "gql_mutation_delete_families_perms",
            "gql_query_insurees_perms",
            "gql_mutation_create_insurees_perms",
            "gql_mutation_update_insurees_perms",
            "gql_mutation_delete_insurees_perms",
            "gql_query_insuree_inquire_perms",
            "gql_query_policies_perms",
            "gql_mutation_create_policies_perms",
            "gql_mutation_edit_policies_perms",
            "gql_mutation_delete_policies_perms",
            "gql_mutation_renew_policies_perms",
            "gql_query_premiums_perms",
            "gql_mutation_create_premiums_perms",
            "gql_mutation_update_premiums_perms",
            "gql_mutation_delete_premiums_perms",
            "gql_query_claims_perms",
            "gql_mutation_deliver_claim_feedback_perms",
        ],
    },
    "ClaimAdministrator": {
        "is_system": 16,
        "perm_names": [
            "gql_query_policies_perms",
            "gql_query_insuree_perms",
            "gql_mutation_create_claims_perms",
            "gql_mutation_update_claims_perms",
            "gql_query_claims_perms",
            "gql_query_health_facilities_perms",
            "gql_query_medical_services_perms",
            "gql_query_medical_items_perms",
        ],
    },
    "MedicalOfficer": {
        "is_system": 16,
        "perm_names": [
            "gql_query_claims_perms",
            "gql_mutation_create_claims_perms",
            "gql_mutation_update_claims_perms",
            "gql_mutation_submit_claims_perms",
            "gql_mutation_process_claims_perms",
            "gql_reports_claim_history_report_perms",
        ],
    },
    "SchemeAdministrator": {
        "is_system": 32,
        "perm_names": [
            "gql_query_insuree_inquire_perms",
            "gql_query_locations_perms",
            "gql_query_health_facilities_perms",
            "gql_mutation_create_locations_perms",
            "gql_mutation_edit_locations_perms",
            "gql_mutation_delete_locations_perms",
            "gql_mutation_move_location_perms",
            "gql_mutation_create_region_locations_perms",
            "gql_mutation_create_health_facilities_perms",
            "gql_mutation_edit_health_facilities_perms",
            "gql_mutation_delete_health_facilities_perms",
            "gql_query_medical_items_perms",
            "gql_query_medical_services_perms",
            "gql_mutation_medical_items_add_perms",
            "gql_mutation_medical_items_update_perms",
            "gql_mutation_medical_items_delete_perms",
            "gql_mutation_medical_services_add_perms",
            "gql_mutation_medical_services_update_perms",
            "gql_mutation_medical_services_delete_perms",
            "gql_query_pricelists_medical_items_perms",
            "gql_mutation_pricelists_medical_items_add_perms",
            "gql_mutation_pricelists_medical_items_update_perms",
            "gql_mutation_pricelists_medical_items_delete_perms",
            "gql_mutation_pricelists_medical_items_duplicate_perms",
            "gql_query_pricelists_medical_services_perms",
            "gql_mutation_pricelists_medical_services_add_perms",
            "gql_mutation_pricelists_medical_services_update_perms",
            "gql_mutation_pricelists_medical_services_delete_perms",
            "gql_mutation_pricelists_medical_services_duplicate_perms",
            "gql_query_products_perms",
            "gql_mutation_products_add_perms",
            "gql_mutation_products_edit_perms",
            "gql_mutation_products_delete_perms",
            "gql_mutation_products_duplicate_perms",
            "gql_query_insurees_perms",
            "gql_query_families_perms",
            "gql_query_insuree_policy_perms",
            "gql_mutation_create_families_perms",
            "gql_mutation_update_families_perms",
            "gql_mutation_delete_families_perms",
            "gql_mutation_create_insurees_perms",
            "gql_mutation_update_insurees_perms",
            "gql_mutation_delete_insurees_perms",
            "gql_query_policies_perms",
            "gql_query_policies_by_insuree_perms",
            "gql_query_policies_by_family_perms",
            "gql_query_eligibilities_perms",
            "gql_mutation_create_policies_perms",
            "gql_mutation_renew_policies_perms",
            "gql_mutation_edit_policies_perms",
            "gql_mutation_suspend_policies_perms",
            "gql_mutation_delete_policies_perms",
            "gql_query_premiums_perms",
            "gql_mutation_create_premiums_perms",
            "gql_mutation_update_premiums_perms",
            "gql_mutation_delete_premiums_perms",
            "gql_query_payers_perms",
            "gql_mutation_payer_add_perms",
            "gql_mutation_payer_update_perms",
            "gql_mutation_payer_delete_perms",
            "gql_query_payments_perms",
            "gql_mutation_create_payments_perms",
            "gql_mutation_update_payments_perms",
            "gql_mutation_delete_payments_perms",
            "gql_query_claims_perms",
            "gql_mutation_create_claims_perms",
            "gql_mutation_update_claims_perms",
            "gql_mutation_load_claims_perms",
            "gql_mutation_submit_claims_perms",
            "gql_mutation_select_claim_feedback_perms",
            "gql_mutation_bypass_claim_feedback_perms",
            "gql_mutation_skip_claim_feedback_perms",
            "gql_mutation_deliver_claim_feedback_perms",
            "gql_mutation_select_claim_review_perms",
            "gql_mutation_bypass_claim_review_perms",
            "gql_mutation_skip_claim_review_perms",
            "gql_mutation_deliver_claim_review_perms",
            "gql_mutation_process_claims_perms",
            "gql_mutation_restore_claims_perms",
            "gql_mutation_delete_claims_perms",
            "claim_print_perms",
            "gql_query_batch_runs_perms",
            "gql_mutation_process_batch_perms",
            "gql_reports_capitation_payment_perms",
            "account_preview_perms",
            "registers_perms",
            "registers_diagnoses_perms",
            "registers_health_facilities_perms",
            "registers_locations_perms",
            "registers_items_perms",
            "registers_services_perms",
            "extracts_master_data_perms",
            "extracts_officer_feedbacks_perms",
            "extracts_officer_renewals_perms",
            "extracts_phone_extract_perms",
            "extracts_upload_claims_perms",
            "gql_query_report_perms",
            "gql_reports_primary_operational_indicator_policies_perms",
            "gql_reports_primary_operational_indicators_claims_perms",
            "gql_reports_derived_operational_indicators_perms",
            "gql_reports_contribution_collection_perms",
            "gql_reports_product_sales_perms",
            "gql_reports_contribution_distribution_perms",
            "gql_reports_user_activity_perms",
            "gql_reports_enrolment_performance_indicators_perms",
            "gql_reports_status_of_register_perms",
            "gql_reports_insuree_without_photos_perms",
            "gql_reports_payment_category_overview_perms",
            "gql_reports_matching_funds_perms",
            "gql_reports_claim_overview_report_perms",
            "gql_reports_percentage_referrals_perms",
            "gql_reports_families_insurees_overview_perms",
            "gql_reports_pending_insurees_perms",
            "gql_reports_renewals_perms",
            "gql_reports_capitation_payment_perms",
            "gql_reports_rejected_photo_perms",
            "gql_reports_contribution_payment_perms",
            "gql_reports_control_number_assignment_perms",
            "gql_reports_overview_of_commissions_perms",
            "gql_reports_claim_history_report_perms",
            "gql_mutation_report_add_perms",
            "gql_mutation_report_edit_perms",
            "gql_mutation_report_delete_perms",
        ],
    },
    "Receptionist": {
        "is_system": 128,
        "perm_names": [
            "gql_query_families_perms",
            "gql_query_insurees_perms",
            "gql_query_insuree_inquire_perms",
            "gql_query_policies_perms",
            "gql_query_premiums_perms",
        ],
    },
    "ClaimContributor": {
        "is_system": 512,
        "perm_names": [
            "gql_query_claims_perms",
            "gql_mutation_create_claims_perms",
            "gql_mutation_update_claims_perms",
        ],
    },
    "HFAdministrator": {
        "is_system": 524288,
        "perm_names": _HF_ADMIN_PERMS,
    },
    "OfflineAdministrator": {
        "is_system": 1048576,
        "perm_names": _HF_ADMIN_PERMS,
    },
}


def role_right_ids(perm_names):
    """Resolve permission names as they appear in the module DEFAULT configs into right ids."""
    flat_perms = {}
    for app_perms in collect_all_gql_permissions().values():
        flat_perms.update(app_perms)

    right_ids = []
    for perm_name in perm_names:
        if perm_name not in flat_perms:
            # message is asserted verbatim by core.tests.test_create_test_role
            raise Exception(f"Permission {perm_name} not found")
        right_ids.extend(flat_perms[perm_name])

    return list(set(right_ids))


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role

    name = factory.Sequence(lambda n: f"TestRole{n}")
    is_system = 0
    is_blocked = False
    audit_user_id = -1
    validity_from = factory.LazyFunction(datetime.datetime.now)


class RoleRightFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoleRight

    role = factory.SubFactory(RoleFactory)
    right_id = 1
    audit_user_id = -1
    validity_from = factory.LazyFunction(datetime.datetime.now)
