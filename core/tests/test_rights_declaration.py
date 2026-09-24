from unittest.mock import patch

from django.test import TestCase

from core.rights_declaration import RightsDeclaration

DJANGO_PERMS = {
    "widget": {
        "query": ("demo.view_widget", 999001),
        "create": ("demo.add_widget", 999002),
        # deliberate sharing: archiving is a modification
        "update": ("demo.change_widget", 999003),
        "archive": ("demo.archive_widget", 999003),
    },
}
PERM_CFG = {
    "gql_query_widgets_perms": ("widget", "query"),
    "gql_mutation_create_widgets_perms": ("widget", "create"),
    "gql_mutation_update_widgets_perms": ("widget", "update"),
    "gql_mutation_archive_widgets_perms": ("widget", "archive"),
}


class RightsDeclarationTestCase(TestCase):
    def setUp(self):
        self.rights = RightsDeclaration("core", DJANGO_PERMS, PERM_CFG)

    # --- declaration ------------------------------------------------------
    def test_perms_returns_the_declared_default(self):
        self.assertEqual(self.rights.perms("widget", "query"), ["999001"])

    def test_perms_multi_action_is_any_of(self):
        """`has_perms` does an OR: the list means "one or the other"."""
        self.assertEqual(
            self.rights.perms("widget", "query", "create"), ["999001", "999002"]
        )

    def test_django_names(self):
        self.assertEqual(
            self.rights.django_perm_names("widget", "query"), ["demo.view_widget"]
        )

    def test_default_cfg_covers_every_key(self):
        self.assertEqual(
            self.rights.default_cfg(),
            {
                "gql_query_widgets_perms": ["999001"],
                "gql_mutation_create_widgets_perms": ["999002"],
                "gql_mutation_update_widgets_perms": ["999003"],
                "gql_mutation_archive_widgets_perms": ["999003"],
            },
        )

    def test_shared_id_keeps_distinct_django_names(self):
        self.assertEqual(
            self.rights.perms("widget", "update"), self.rights.perms("widget", "archive")
        )
        self.assertNotEqual(
            self.rights.django_perm_names("widget", "update"),
            self.rights.django_perm_names("widget", "archive"),
        )

    def test_unknown_entity_or_action_raises(self):
        with self.assertRaises(KeyError):
            self.rights.perms("nosuch", "query")
        with self.assertRaises(KeyError):
            self.rights.perms("widget", "nosuch")

    def test_config_key_pointing_at_an_undeclared_action_is_refused(self):
        """
        The trap this closes: the key would yield [], hence access open to all.
        """
        with self.assertRaises(KeyError):
            RightsDeclaration(
                "core", DJANGO_PERMS, {"gql_query_x_perms": ("widget", "nosuch")}
            )

    # --- read at runtime --------------------------------------------------
    def test_configured_reads_the_app_config_at_call_time(self):
        from core.apps import CoreConfig

        with patch.object(CoreConfig, "gql_query_widgets_perms", ["888888"], create=True):
            self.assertEqual(self.rights.configured("widget", "query"), ["888888"])
        # and the declared default has not moved
        self.assertEqual(self.rights.perms("widget", "query"), ["999001"])

    def test_configured_returns_none_for_an_undeclared_action(self):
        """None means "no rule": the caller must fail closed."""
        self.assertIsNone(self.rights.configured("widget", "nosuch"))

    def test_configured_reports_an_empty_override(self):
        from core.apps import CoreConfig

        with patch.object(CoreConfig, "gql_query_widgets_perms", [], create=True):
            with self.assertLogs("core.rights_declaration", level="WARNING") as logs:
                self.assertEqual(self.rights.configured("widget", "query"), [])
        self.assertIn("granted to everybody", "".join(logs.output))

    # --- the modules actually converted -----------------------------------
    def test_converted_modules_share_the_generic(self):
        from claim.apps import RIGHTS as CLAIM
        from contract.apps import RIGHTS as CONTRACT
        from core.apps import RIGHTS as CORE
        from insuree.apps import RIGHTS as INSUREE

        for rights in (CORE, CLAIM, INSUREE, CONTRACT):
            with self.subTest(module=rights.module_name):
                self.assertIsInstance(rights, RightsDeclaration)
                # every declared config key must exist on the AppConfig, otherwise
                # `__load_config` ignores it and reading it raises AttributeError
                for entity, action in rights.perm_cfg.values():
                    self.assertIsNotNone(
                        rights.configured(entity, action),
                        f"{rights.module_name}.{entity}.{action} is unreadable",
                    )
