"""
OP-3353 / CVE-2026-82491: a client-supplied column path may only follow relations the
caller is allowed to read.

`authorized_field_path` walks a Django ``a__b__c`` path over the model metadata: only
forward foreign keys and one-to-one relations are followed, each relation crossed needs
the ``query`` right of the related model, a segment that looks like a secret is refused,
and keys under a JSON field must be plain identifiers.
"""

from django.test import TestCase

from core.rights_scope import (
    FIELD_PATH_INVALID,
    FIELD_PATH_SECRET,
    FIELD_PATH_UNAUTHORIZED,
    authorized_field_path,
    field_path_refusal,
    model_rights,
)


class _RightsUser:
    """Holds exactly the given rights; `has_perms` follows the User contract (any of)."""

    def __init__(self, *right_lists):
        self.granted = {str(r) for rights in right_lists for r in rights}

    def has_perms(self, perm_list, *args, **kwargs):
        if not perm_list:
            return True
        return any(str(p) in self.granted for p in perm_list)


class AuthorizedFieldPathTestCase(TestCase):
    def setUp(self):
        from individual.models import Group, GroupIndividual, Individual

        self.Individual = Individual
        self.Group = Group
        self.GroupIndividual = GroupIndividual
        self.individual_rights = model_rights(Individual, "query")
        self.group_rights = model_rights(Group, "query")
        self.everything = _RightsUser(self.individual_rights, self.group_rights)

    # --- the columns the UI sends --------------------------------------------
    def test_own_concrete_columns_are_allowed_without_any_relation_right(self):
        user = _RightsUser()
        for path in ("id", "first_name", "last_name", "dob", "json_ext"):
            self.assertTrue(
                authorized_field_path(user, self.Individual, path), path
            )

    def test_json_ext_key_is_allowed_when_it_is_a_plain_identifier(self):
        user = _RightsUser()
        self.assertTrue(
            authorized_field_path(user, self.Individual, "json_ext__educated_level")
        )

    def test_own_foreign_key_column_is_allowed(self):
        """`group` alone is the id stored on the root row: no join, no right."""
        self.assertTrue(
            authorized_field_path(_RightsUser(), self.GroupIndividual, "group")
        )

    def test_foreign_key_followed_by_its_target_field_is_the_own_column(self):
        """`group.id` is what the group beneficiary export sends: no join, no right."""
        self.assertTrue(
            authorized_field_path(_RightsUser(), self.GroupIndividual, "group__id")
        )

    def test_related_column_is_allowed_with_the_related_models_right(self):
        user = _RightsUser(self.individual_rights)
        self.assertTrue(
            authorized_field_path(
                user, self.GroupIndividual, "individual__first_name"
            )
        )

    # --- relations without the right ----------------------------------------
    def test_related_column_is_refused_without_the_related_models_right(self):
        user = _RightsUser(self.individual_rights)
        self.assertEqual(
            field_path_refusal(user, self.GroupIndividual, "group__code"),
            FIELD_PATH_UNAUTHORIZED,
        )

    def test_relation_to_a_model_that_declares_no_right_is_refused(self):
        """`core.User` declares no `get_rights`: fail closed."""
        self.assertEqual(
            field_path_refusal(self.everything, self.Individual, "user_created__username"),
            FIELD_PATH_UNAUTHORIZED,
        )

    # --- structurally refused, whatever the rights ---------------------------
    def test_secret_segment_is_refused(self):
        self.assertEqual(
            field_path_refusal(
                self.everything, self.Individual, "user_created__i_user__password"
            ),
            FIELD_PATH_SECRET,
        )

    def test_secret_json_key_is_refused(self):
        self.assertEqual(
            field_path_refusal(self.everything, self.Individual, "json_ext__api_token"),
            FIELD_PATH_SECRET,
        )

    def test_reverse_relation_is_refused(self):
        self.assertEqual(
            field_path_refusal(
                self.everything, self.Individual, "groupindividuals__group__code"
            ),
            FIELD_PATH_INVALID,
        )

    def test_unknown_field_is_refused(self):
        self.assertEqual(
            field_path_refusal(self.everything, self.Individual, "no_such_field"),
            FIELD_PATH_INVALID,
        )

    def test_lookup_or_transform_after_a_concrete_field_is_refused(self):
        self.assertEqual(
            field_path_refusal(self.everything, self.Individual, "dob__year"),
            FIELD_PATH_INVALID,
        )

    def test_json_key_that_is_not_a_plain_identifier_is_refused(self):
        for path in ("json_ext__a-b", "json_ext__a b", "json_ext__0abc", "json_ext__"):
            self.assertEqual(
                field_path_refusal(self.everything, self.Individual, path),
                FIELD_PATH_INVALID,
                path,
            )

    def test_empty_path_is_refused(self):
        self.assertEqual(
            field_path_refusal(self.everything, self.Individual, ""),
            FIELD_PATH_INVALID,
        )
