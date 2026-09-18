"""
Les points d'entree GraphQL qui n'exigeaient aucun droit en exigent un.

Chacun de ces dix cas etait silencieux : soit aucun controle, soit un helper de
permission ecrit mais jamais appele, soit un `has_perms` commente. Le test lit le code
du resolver ou de la mutation (commentaires retires, pour qu'un controle commente ne
compte pas) et verifie qu'un droit y est bien reference.

C'est volontairement statique : monter un utilisateur et une requete pour chacun des
dix modules couterait cher et testerait surtout graphene. Ce qui doit etre verrouille
ici, c'est qu'un controle existe et ne disparaisse pas a la prochaine refonte.
"""

import ast
import inspect
import re
import textwrap

from django.test import TestCase

PERM_CALL = re.compile(
    r"\bhas_perms?\s*\(|_check_permissions\s*\(|has_model_right\s*\(")


def _body(obj):
    """Source de `obj`, commentaires retires via un aller-retour par l'AST."""
    source = textwrap.dedent(inspect.getsource(obj))
    return ast.unparse(ast.parse(source))


class RbacCallSiteTestCase(TestCase):
    def _assert_checks(self, obj, label):
        body = _body(obj)
        self.assertRegex(
            body, PERM_CALL,
            f"{label} ne verifie aucun droit (un controle commente ne compte pas)")

    # --- 1. payroll : la config de passerelle expose une cle d'API ---------
    def test_payment_gateway_config(self):
        from payroll.apps import PayrollConfig
        from payroll.schema import Query

        self._assert_checks(Query.resolve_payment_gateway_config, "paymentGatewayConfig")
        self.assertEqual(PayrollConfig.gql_payment_gateway_config_perms, ["202005"])

    # --- 2. invoice : helper ecrit mais jamais appele ----------------------
    def test_bill_payment(self):
        from invoice.gql.bill_payment.query import BillPaymentQueryMixin

        self._assert_checks(BillPaymentQueryMixin.resolve_bill_payment, "billPayment")

    # --- 3. workflow : module sans aucun droit ----------------------------
    def test_workflow(self):
        from workflow.apps import WorkflowConfig
        from workflow.schema import Query

        self._assert_checks(Query.resolve_workflow, "workflow")
        self.assertEqual(WorkflowConfig.gql_workflow_search_perms, ["210001"])

    def test_workflow_no_longer_borrows_individual_right(self):
        """Emprunter le droit d'individual liait les workflows a une autre entite."""
        from workflow.schema import Query

        self.assertNotIn("IndividualConfig", _body(Query._check_permissions))

    # --- 4. tasks_management : le seul type sans get_queryset -------------
    def test_task_group(self):
        from tasks_management.schema import Query

        self._assert_checks(Query.resolve_task_group, "taskGroup")

    # --- 5. claim_sampling : has_perms commente ---------------------------
    def test_create_claim_sampling_batch(self):
        from claim_sampling.gql_mutations import CreateClaimSamplingBatchMutation

        self._assert_checks(CreateClaimSamplingBatchMutation, "createClaimSamplingBatch")

    # --- 6 et 7. contract : deux mixins restes sur l'authentification -----
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

    # --- 8. contribution_plan : trois oracles d'existence -----------------
    def test_contribution_plan_code_validators(self):
        from contribution_plan.schema import Query

        for name in (
            "resolve_validate_contribution_plan_code",
            "resolve_validate_contribution_plan_bundle_code",
            "resolve_validate_payment_plan_code",
        ):
            with self.subTest(resolver=name):
                self._assert_checks(getattr(Query, name), name)

    # --- 9. controls : module sans aucun droit ----------------------------
    def test_controls(self):
        from controls.apps import ControlsConfig
        from controls.schema import Query

        self._assert_checks(Query.resolve_control_str, "controlStr")
        self.assertEqual(ControlsConfig.gql_query_controls_perms, ["211001"])

    # --- 10. individual ---------------------------------------------------
    def test_global_schema(self):
        from individual.schema import Query

        self._assert_checks(Query.resolve_global_schema, "globalSchema")

    # --- les trois droits neufs doivent etre grantables -------------------
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
                    "un droit absent du catalogue ne peut etre accorde a personne")
