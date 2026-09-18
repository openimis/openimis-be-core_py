"""
Cross-module guards on the right declarations.

Two failure modes these catch, both silent:

  * a ``*_perms`` entry left at ``[]``. ``has_perms([])`` returns True, so an empty
    right list does not deny - it grants the action to everyone, authenticated or not.
    Several GraphQL queries were effectively public for exactly this reason.
  * a right id used by a module but absent from ``permissions_map.json``, the catalog
    the solution builder seeds roles from. A right nothing can grant is a right nobody
    can hold, so the feature it gates is unreachable rather than protected.

Both are asserted across every installed module, so a new module or a new right is
covered without touching this file.
"""

import ast
import json
import os
import re
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.test import TestCase

# Declared-empty on purpose. Each entry needs a comment in its apps.py saying why.
#   medical.gql_query_diagnosis_perms - no sibling read right to alias onto (medical's
#   reads are medical_items and medical_services, and a Diagnosis is neither), and the
#   module's sibling reads are themselves deliberately open under OMT-281. Settling it
#   is a decision, not a rename.
KNOWN_EMPTY = {
    ("medical", "gql_query_diagnosis_perms"),
}

# Right ids a module names but the catalog does not list, that are nonetheless
# grantable. `has_perms` ORs a right list, so where a config key holds several ids only
# one of them has to be catalogued for a role to satisfy it - the rest are redundant
# alternates, not rights nobody can hold.
#
# tools' register keys are each ["131000", <even>, <odd>] and the odd one is catalogued
# (tools.registers_diagnoses = 131001, and so on), so a role granted that has access;
# 131000 is the blanket "any register" variant. Same for extracts_phone_extract, whose
# catalogued 131103 sits beside 131102. Naming the others would mean asserting a
# read/write split that the code does not make - tools/views.py gates both the download
# and the upload endpoint with the *same* key - so they are left out of the catalog
# rather than given invented names.
KNOWN_UNCATALOGUED = {
    "131000", "131002", "131004", "131006", "131008", "131010", "131102",
}

# The assembly's catalog, not the package's: modules are installed from a separate
# tree, so this is resolved from BASE_DIR rather than relative to this file.
PERMISSIONS_MAP = Path(settings.BASE_DIR) / "permissions_map.json"


def _iter_declared_rights():
    """(module_label, config_key, [right ids]) for every *_perms in every apps.py."""
    for app_config in django_apps.get_app_configs():
        apps_py = Path(app_config.path) / "apps.py"
        if not apps_py.exists():
            continue
        try:
            tree = ast.parse(apps_py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if not key.value.endswith("_perms"):
                    continue
                if not isinstance(value, ast.List):
                    continue
                try:
                    ids = [str(ast.literal_eval(e)) for e in value.elts]
                except Exception:
                    continue
                yield app_config.label, key.value, ids


class PermissionDeclarationConsistencyTestCase(TestCase):
    def test_no_right_list_is_empty(self):
        empty = [
            f"{label}.{key}"
            for label, key, ids in _iter_declared_rights()
            if not ids and (label, key) not in KNOWN_EMPTY
        ]
        self.assertEqual(
            empty,
            [],
            "empty right lists are granted to everyone by `has_perms`; give each a "
            "right id, or add it to KNOWN_EMPTY with the reason in its apps.py",
        )

    def test_known_empty_entries_still_exist(self):
        """Stops the allowlist outliving the thing it excuses."""
        declared = {
            (label, key) for label, key, _ in _iter_declared_rights()
        }
        stale = [f"{a}.{b}" for a, b in KNOWN_EMPTY if (a, b) not in declared]
        self.assertEqual(stale, [], f"KNOWN_EMPTY names entries that are gone: {stale}")

    def test_every_declared_right_id_is_in_the_permissions_map(self):
        """
        The map is what the solution builder seeds roles from: an id missing from it
        cannot be granted to anyone.
        """
        catalog = set(json.loads(PERMISSIONS_MAP.read_text(encoding="utf-8")).values())
        missing = sorted(
            {
                f"{rid} ({label}.{key})"
                for label, key, ids in _iter_declared_rights()
                for rid in ids
                if rid not in catalog and rid not in KNOWN_UNCATALOGUED
            }
        )
        self.assertEqual(
            missing, [], f"right ids used by a module but absent from the catalog: {missing}"
        )

    def test_known_uncatalogued_ids_are_still_referenced(self):
        """Stops that allowlist outliving the ids it excuses."""
        declared = {
            rid for _, _, ids in _iter_declared_rights() for rid in ids
        }
        stale = sorted(KNOWN_UNCATALOGUED - declared)
        self.assertEqual(
            stale, [], f"KNOWN_UNCATALOGUED names ids no module uses: {stale}"
        )

    def test_known_uncatalogued_ids_have_a_catalogued_alternative(self):
        """
        The reason they are tolerated: every config key holding one also holds an id
        the catalog lists, so a role can still satisfy the check.
        """
        catalog = set(json.loads(PERMISSIONS_MAP.read_text(encoding="utf-8")).values())
        orphaned = sorted(
            {
                f"{label}.{key}"
                for label, key, ids in _iter_declared_rights()
                if set(ids) & KNOWN_UNCATALOGUED and not (set(ids) & catalog)
            }
        )
        self.assertEqual(
            orphaned,
            [],
            f"only uncatalogued ids - nothing can be granted for: {orphaned}",
        )

    def test_right_ids_look_like_right_ids(self):
        bad = sorted(
            {
                f"{label}.{key} = {rid!r}"
                for label, key, ids in _iter_declared_rights()
                for rid in ids
                if not re.fullmatch(r"\d{6}", rid)
            }
        )
        self.assertEqual(bad, [], f"a right id is a six digit decimal string: {bad}")
