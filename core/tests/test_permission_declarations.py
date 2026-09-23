"""
Guards on the permission declarations in `core.apps`.

The rights themselves are enforced elsewhere; what these tests protect is the
declaration layer, where the failures are silent rather than loud:

  * `has_perms([])` returns True by design (`core.models.user.User.has_perms`), so a
    right list that resolves to empty grants the action to everyone. Several GraphQL
    queries were effectively public for exactly this reason.
  * A `_perms` key declared in DEFAULT_CFG but never assigned onto `CoreConfig` is
    unreadable at the call site - `gql_query_users_profile_perms` sat like that, with a
    real right (122000) that nothing could enforce.
  * The numeric right is what is stored on a role, so changing one silently revokes
    access for every role already granted it. The expected ids are pinned below: an
    intentional change means updating this test *and* writing the data migration.
"""

from django.apps import apps as django_apps
from django.test import TestCase

from core.apps import (
    DJANGO_PERMS,
    CoreConfig,
    _PERM_CFG,
    django_perms,
    perms,
)


# The right ids as deployed. Changing one is a breaking change for existing roles.
EXPECTED_RIGHTS = {
    "gql_query_users_perms": ["121701"],
    "gql_query_users_profile_perms": ["122000"],
    "gql_mutation_create_users_perms": ["121702"],
    "gql_mutation_update_users_perms": ["121703"],
    "gql_mutation_delete_users_perms": ["121704"],
    "gql_query_roles_perms": ["122001"],
    "gql_mutation_create_roles_perms": ["122002"],
    "gql_mutation_update_roles_perms": ["122003"],
    "gql_mutation_replace_roles_perms": ["122006"],
    "gql_mutation_duplicate_roles_perms": ["122005"],
    "gql_mutation_delete_roles_perms": ["122004"],
    "gql_query_enrolment_officers_perms": ["121501"],
    "gql_mutation_create_enrolment_officers_perms": ["121502"],
    "gql_mutation_update_enrolment_officers_perms": ["121503"],
    "gql_mutation_delete_enrolment_officers_perms": ["121504"],
    "gql_query_claim_administrator_perms": ["121601"],
    "gql_mutation_create_claim_administrator_perms": ["121602"],
    "gql_mutation_update_claim_administrator_perms": ["121603"],
    "gql_mutation_delete_claim_administrator_perms": ["121604"],
    "gql_query_enable_viewing_masked_data_perms": ["900101"],
}


class PermissionDeclarationTestCase(TestCase):
    def test_right_ids_unchanged(self):
        """Pins the deployed right ids - see EXPECTED_RIGHTS."""
        self.assertEqual(
            {key: getattr(CoreConfig, key) for key in EXPECTED_RIGHTS},
            EXPECTED_RIGHTS,
        )

    def test_perm_cfg_covers_every_declared_right(self):
        declared = {
            (entity, action)
            for entity, actions in DJANGO_PERMS.items()
            for action in actions
        }
        self.assertEqual(
            set(_PERM_CFG.values()),
            declared,
            "every DJANGO_PERMS action needs a _perms config key, and vice versa",
        )

    def test_perm_cfg_matches_config_attributes(self):
        """
        Each _PERM_CFG key must exist on CoreConfig, so the call sites can read it.
        """
        missing = [key for key in _PERM_CFG if not hasattr(CoreConfig, key)]
        self.assertEqual(missing, [], f"declared but absent from CoreConfig: {missing}")

    def test_no_right_list_is_empty(self):
        """An empty list is `has_perms` -> True, i.e. granted to everyone."""
        empty = [key for key in _PERM_CFG if not getattr(CoreConfig, key)]
        self.assertEqual(empty, [], f"empty right lists grant access to all: {empty}")

    def test_attributes_carry_the_declared_right(self):
        for key, (entity, action) in _PERM_CFG.items():
            with self.subTest(key=key):
                self.assertEqual(getattr(CoreConfig, key), perms(entity, action))

    def test_right_ids_are_unique_within_core(self):
        seen = {}
        for entity, actions in DJANGO_PERMS.items():
            for action, (_, right_id) in actions.items():
                seen.setdefault(right_id, []).append(f"{entity}.{action}")
        shared = {rid: who for rid, who in seen.items() if len(who) > 1}
        self.assertEqual(shared, {}, f"one right id for several actions: {shared}")

    def test_django_permission_names_are_unique(self):
        seen = {}
        for entity, actions in DJANGO_PERMS.items():
            for action, (name, _) in actions.items():
                seen.setdefault(name, []).append(f"{entity}.{action}")
        shared = {name: who for name, who in seen.items() if len(who) > 1}
        self.assertEqual(shared, {}, f"one django name for several actions: {shared}")

    def test_unknown_entity_or_action_raises(self):
        """
        The point of routing rights through `perms()`: a typo fails at import time
        instead of yielding [], which would read as "granted to everyone".
        """
        with self.assertRaises(KeyError):
            perms("nosuchentity", "query")
        with self.assertRaises(KeyError):
            perms("user", "nosuchaction")
        with self.assertRaises(KeyError):
            django_perms("user", "nosuchaction")

    def test_multi_action_returns_every_right(self):
        """`has_perms` ORs the list, so this is the "any of" form."""
        self.assertEqual(
            perms("role", "update", "replace"),
            ["122003", "122006"],
        )

    def test_crud_django_names_match_the_real_models(self):
        """
        The `query`/`create`/`update`/`delete` names must be the ones django generates
        at post_migrate (`<app_label>.<action>_<model>`), or they can never be granted.
        Business actions are skipped: they need `Meta.permissions` first.
        """
        prefixes = {"query": "view", "create": "add", "update": "change", "delete": "delete"}
        model_for_entity = {
            "user": "User",
            "role": "Role",
            "enrolmentOfficer": "Officer",
            "claimAdministrator": "ClaimAdmin",
        }
        for entity, model_name in model_for_entity.items():
            model = django_apps.get_model("core", model_name)
            for action, prefix in prefixes.items():
                with self.subTest(entity=entity, action=action):
                    expected = (
                        f"{model._meta.app_label}."
                        f"{prefix}_{model._meta.model_name}"
                    )
                    self.assertEqual(DJANGO_PERMS[entity][action][0], expected)
