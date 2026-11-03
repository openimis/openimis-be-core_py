import json

from django.apps import apps as django_apps
from django.test import TestCase

from core.models import ModuleConfiguration


class RightsNotConfigurableTestCase(TestCase):
    def test_stored_rights_are_ignored_and_reported(self):
        stored = {
            "gql_query_claims_perms": ["999999"],
            "claim_print_perms": ["999998"],
            "default_validations_disabled": True,
        }
        with self.assertLogs("core.models.base", level="WARNING") as logs:
            merged = ModuleConfiguration._without_rights("claim", stored)
        self.assertNotIn("gql_query_claims_perms", merged)
        self.assertNotIn("claim_print_perms", merged)
        # what is not a right stays configurable
        self.assertEqual(merged["default_validations_disabled"], True)
        message = "".join(logs.output)
        self.assertIn("gql_query_claims_perms", message)
        self.assertIn("are no longer configurable", message)

    def test_a_config_without_rights_is_untouched(self):
        stored = {"default_validations_disabled": True}
        self.assertEqual(ModuleConfiguration._without_rights("claim", stored), stored)

    def test_get_or_default_drops_a_stored_override(self):
        """End to end: a database row can no longer change a right."""
        default = {"gql_query_claims_perms": ["111001"], "other": 1}
        ModuleConfiguration.objects.create(
            module="claim_test_rights",
            layer="be",
            version="1",
            config=json.dumps({"gql_query_claims_perms": ["999999"], "other": 2}),
        )
        merged = ModuleConfiguration.get_or_default("claim_test_rights", default)
        self.assertEqual(merged["gql_query_claims_perms"], ["111001"])
        self.assertEqual(merged["other"], 2, "the rest of the config still applies")

    def test_the_hot_reload_path_also_drops_a_stored_override(self):
        """The hot reload goes through `_cfg`, not through `get_or_default`.

        `core.module_config_registry.reload_module_configuration` hands the config
        back to every module after a database write, and the three modules that
        subscribe to it (`grievance_social_protection`, `individual`,
        `social_protection`) read `instance._cfg`. A filter placed only in
        `get_or_default` would therefore let that path reintroduce a stored right
        — on the first save of the config, not at startup, which would make it
        hard to see. That is why the filter lives in `_cfg`.
        """
        instance = ModuleConfiguration(
            module="claim_test_reload",
            layer="be",
            version="1",
            config=json.dumps(
                {"gql_query_claims_perms": ["999999"], "other": 2}
            ),
        )
        self.assertNotIn("gql_query_claims_perms", instance._cfg)
        self.assertEqual(instance._cfg["other"], 2)

        # and the filter follows a reassignment of `config` (the admin case)
        instance.config = json.dumps({"claim_print_perms": ["999998"], "other": 3})
        self.assertNotIn("claim_print_perms", instance._cfg)
        self.assertEqual(instance._cfg["other"], 3)

    def test_nested_stored_rights_are_also_ignored(self):
        """
        The filter is recursive: api_fhir_r4 declared its subscription rights in a
        nested block, which passed a filter limited to the top level.
        """
        stored = {
            "R4_fhir_subscription_config": {
                "fhir_sub_search_perms": ["999999"],
                "fhir_sub_channel_rest_hook": "rest-hook",
            },
        }
        with self.assertLogs("core.models.base", level="WARNING"):
            merged = ModuleConfiguration._without_rights("api_fhir_r4", stored)
        nested = merged["R4_fhir_subscription_config"]
        self.assertNotIn("fhir_sub_search_perms", nested)
        self.assertEqual(nested["fhir_sub_channel_rest_hook"], "rest-hook")

    def test_every_discovered_right_comes_from_an_attribute(self):
        """
        `collect_all_gql_permissions` feeds the roles screen, `create_test_role` and
        `generate_permissions_map`: what it sees must be exactly what the modules
        declare.
        """
        from core.utils import collect_all_gql_permissions

        for app, perms in collect_all_gql_permissions().items():
            app_config = next(
                ac for ac in django_apps.get_app_configs() if ac.name == app
            )
            for name, ids in perms.items():
                with self.subTest(app=app, right=name):
                    self.assertEqual(
                        [str(v) for v in getattr(app_config, name)], ids
                    )
