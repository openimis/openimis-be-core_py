"""
`core.rights_scope`: an action's rights, declared on the model, inherited from a parent.

What matters here is that the declaration is read at call time (not snapshotted at
import, where the config is still an empty placeholder that `has_perms` grants to
everyone), that a sub-resource inherits its `scope_parent`'s rights, and that an
undeclared action denies rather than allows.
"""

from unittest.mock import patch

from django.test import TestCase

from core.rights_scope import (
    VERB_ACTIONS,
    has_model_right,
    model_rights,
    scope_parent_of,
)
from core.test_helpers import create_right_only_user


class RightsScopeTestCase(TestCase):
    def setUp(self):
        from contract.models import Contract, ContractDetails

        self.parent_model = Contract
        self.child_model = ContractDetails

    # --- declaration ------------------------------------------------------
    def test_scope_parent_resolves_to_the_declared_relation(self):
        self.assertEqual(scope_parent_of(self.child_model), self.parent_model)

    def test_model_without_scope_parent_resolves_to_none(self):
        self.assertIsNone(scope_parent_of(self.parent_model))

    def test_model_declares_its_own_rights(self):
        from contract.apps import ContractConfig

        expected = {
            "query": ContractConfig.gql_query_contract_perms,
            "create": ContractConfig.gql_mutation_create_contract_perms,
            "update": ContractConfig.gql_mutation_update_contract_perms,
            "delete": ContractConfig.gql_mutation_delete_contract_perms,
        }
        for action, rights in expected.items():
            with self.subTest(action=action):
                self.assertEqual(model_rights(self.parent_model, action), list(rights))
                self.assertTrue(rights, f"{action} right is empty")

    def test_rights_are_read_at_call_time_not_snapshotted(self):
        """
        The whole reason `get_rights` is a method: config is only populated in
        `AppConfig.ready()`, so a value captured at import would be the placeholder.
        """
        from contract.apps import ContractConfig

        with patch.object(ContractConfig, "gql_query_contract_perms", ["999999"]):
            self.assertEqual(model_rights(self.parent_model, "query"), ["999999"])
        # and back, without the module being reimported
        self.assertNotEqual(model_rights(self.parent_model, "query"), ["999999"])

    # --- the fallback -----------------------------------------------------
    def test_child_inherits_the_parents_rights(self):
        from contract.apps import ContractConfig

        for action, rights in (
            ("query", ContractConfig.gql_query_contract_perms),
            ("create", ContractConfig.gql_mutation_create_contract_perms),
            ("update", ContractConfig.gql_mutation_update_contract_perms),
            ("delete", ContractConfig.gql_mutation_delete_contract_perms),
        ):
            with self.subTest(action=action):
                self.assertEqual(model_rights(self.child_model, action), list(rights))

    def test_undeclared_action_returns_none(self):
        """None means "no rule", which is not an empty right list."""
        self.assertIsNone(model_rights(self.child_model, "no_such_action"))

    def test_model_with_no_declaration_anywhere_returns_none(self):
        from core.models import ModuleConfiguration

        self.assertIsNone(model_rights(ModuleConfiguration, "query"))

    # --- enforcement ------------------------------------------------------
    def test_undeclared_action_denies(self):
        user = create_right_only_user("rs_undeclared", [])
        self.assertFalse(has_model_right(user, self.child_model, "no_such_action"))

    def test_holding_the_parents_right_allows_the_child_action(self):
        from contract.apps import ContractConfig

        user = create_right_only_user("rs_has", [])
        with patch.object(user, "has_perms", return_value=True) as has_perms:
            self.assertTrue(has_model_right(user, self.child_model, "update"))
        has_perms.assert_called_once_with(
            list(ContractConfig.gql_mutation_update_contract_perms)
        )

    def test_not_holding_the_parents_right_denies_the_child_action(self):
        user = create_right_only_user("rs_hasnt", [])
        with patch.object(user, "has_perms", return_value=False):
            self.assertFalse(has_model_right(user, self.child_model, "update"))

    def test_empty_right_list_is_reported(self):
        """
        `has_perms([])` is True, so an empty declaration grants the action to everyone.
        It is honoured - that is has_perms' contract - but not silently.
        """
        from contract.apps import ContractConfig

        with patch.object(ContractConfig, "gql_mutation_update_contract_perms", []):
            with self.assertLogs("core.rights_scope", level="WARNING") as logs:
                self.assertEqual(model_rights(self.child_model, "update"), [])
        self.assertIn("granted to everyone", "".join(logs.output))

    def test_a_raising_get_rights_is_treated_as_undeclared(self):
        with patch.object(
            self.parent_model, "get_rights", side_effect=RuntimeError("boom")
        ):
            with self.assertLogs("core.rights_scope", level="ERROR"):
                self.assertIsNone(model_rights(self.parent_model, "query"))

    # --- the verb mapping shared with REST/FHIR ---------------------------
    def test_verb_actions_cover_the_write_verbs(self):
        self.assertEqual(VERB_ACTIONS["GET"], "query")
        self.assertEqual(VERB_ACTIONS["POST"], "create")
        self.assertEqual(VERB_ACTIONS["PUT"], "update")
        self.assertEqual(VERB_ACTIONS["PATCH"], "update")
        self.assertEqual(VERB_ACTIONS["DELETE"], "delete")
