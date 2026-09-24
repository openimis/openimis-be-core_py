"""
The GraphQL entry points that required no right at all now require one.

Each of these ten cases was silent: either no check, or a permission helper
written but never called, or a commented-out `has_perms`. The test reads the
source of the resolver or the mutation (comments stripped, so that a
commented-out check does not count) and verifies that a right is indeed
referenced there.

Deliberately static: setting up a user and a query for each of the ten modules
would be expensive and would mostly test graphene. What has to be locked down
here is that a check exists and does not vanish in the next rework.
"""

import ast
import inspect
import re
import textwrap

from django.test import TestCase

PERM_CALL = re.compile(
    r"\bhas_perms?\s*\(|_check_permissions\s*\(|has_model_right\s*\(")


def _body(obj):
    """Source of `obj`, comments stripped through a round trip via the AST."""
    source = textwrap.dedent(inspect.getsource(obj))
    return ast.unparse(ast.parse(source))


class RbacCallSiteTestCase(TestCase):
    def _assert_checks(self, obj, label):
        body = _body(obj)
        self.assertRegex(
            body, PERM_CALL,
            f"{label} checks no right (a commented-out check does not count)")

    # --- 1. payroll: the gateway config exposes an API key -----------------
    def test_payment_gateway_config(self):
        from payroll.apps import PayrollConfig
        from payroll.schema import Query

        self._assert_checks(Query.resolve_payment_gateway_config, "paymentGatewayConfig")
        self.assertEqual(PayrollConfig.gql_payment_gateway_config_perms, ["202005"])

    # --- 2. invoice: helper written but never called -----------------------
    def test_bill_payment(self):
        from invoice.gql.bill_payment.query import BillPaymentQueryMixin

        self._assert_checks(BillPaymentQueryMixin.resolve_bill_payment, "billPayment")

    # --- 3. workflow: module without any right ----------------------------
    def test_workflow(self):
        from workflow.apps import WorkflowConfig
        from workflow.schema import Query

        self._assert_checks(Query.resolve_workflow, "workflow")
        self.assertEqual(WorkflowConfig.gql_workflow_search_perms, ["210001"])

    def test_workflow_no_longer_borrows_individual_right(self):
        """Borrowing individual's right tied workflows to another entity."""
        from workflow.schema import Query

        self.assertNotIn("IndividualConfig", _body(Query._check_permissions))

    # --- 4. tasks_management: the only type without get_queryset ----------
    def test_task_group(self):
        from tasks_management.schema import Query

        self._assert_checks(Query.resolve_task_group, "taskGroup")

    # --- 5. claim_sampling: commented-out has_perms -----------------------
    def test_create_claim_sampling_batch(self):
        from claim_sampling.gql_mutations import CreateClaimSamplingBatchMutation

        self._assert_checks(CreateClaimSamplingBatchMutation, "createClaimSamplingBatch")

    # --- 6 and 7. contract: two mixins left on authentication only --------
    def test_contract_create_invoice(self):
        from contract.gql.gql_mutations.mutations import ContractCreateInvoiceMutationMixin

        self._assert_checks(
            ContractCreateInvoiceMutationMixin._validate_mutation,
            "createContractInvoiceBulk")

    def test_contract_details_from_ph_insuree(self):
        from contract.gql.gql_mutations.mutations import ContractDetailsFromPHInsureeMutationMixin

        self._assert_checks(
            ContractDetailsFromPHInsureeMutationMixin._validate_mutation,
            "createContractDetailsByPhInsuree")

    # --- 8. contribution_plan: three existence oracles --------------------
    def test_contribution_plan_code_validators(self):
        from contribution_plan.schema import Query

        for name in (
            "resolve_validate_contribution_plan_code",
            "resolve_validate_contribution_plan_bundle_code",
            "resolve_validate_payment_plan_code",
        ):
            with self.subTest(resolver=name):
                self._assert_checks(getattr(Query, name), name)

    # --- 9. controls: module without any right ----------------------------
    def test_controls(self):
        from controls.apps import ControlsConfig
        from controls.schema import Query

        self._assert_checks(Query.resolve_control_str, "controlStr")
        self.assertEqual(ControlsConfig.gql_query_controls_perms, ["211001"])

    # --- 10. individual ---------------------------------------------------
    def test_global_schema(self):
        from individual.schema import Query

        self._assert_checks(Query.resolve_global_schema, "globalSchema")

    # --- the three new rights have to be grantable ------------------------
    def test_the_new_rights_are_catalogued(self):
        import json
        from pathlib import Path

        from django.conf import settings

        catalog = set(json.loads(
            (Path(settings.BASE_DIR) / "permissions_map.json").read_text(
                encoding="utf-8")).values())
        for right in ("202005", "210001", "211001"):
            with self.subTest(right=right):
                self.assertIn(
                    right, catalog,
                    "a right missing from the catalogue can be granted to nobody")
