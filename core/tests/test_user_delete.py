"""Deleting a user has to actually delete it (OP-3194).

`set_user_deleted` calls `delete_history()` on every component of a user.
That method was `pass` on both `User` and `InteractiveUser`, so the mutation
wrote nothing and still returned `[]`, which the GraphQL layer reads as
success. These tests pin the two halves: the delete writes a marker, and the
filter the Users searcher uses reads it.
"""

from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from django.test import TestCase

from core.models import InteractiveUser, TechnicalUser, User
from core.schema import set_user_deleted
from core.test_helpers import create_test_interactive_user, create_test_technical_user


def _stored(i_user):
    """Read the row back, bypassing the instance and the manager cache."""
    return InteractiveUser.objects.filter(pk=i_user.pk).values(
        "active", "validity_to"
    ).first()


class UserDeleteTest(TestCase):
    def test_delete_marks_the_interactive_user_both_ways(self):
        user = create_test_interactive_user(username="TestDeleteBoth")
        i_user = user.i_user
        self.assertTrue(_stored(i_user)["active"])
        self.assertIsNone(_stored(i_user)["validity_to"])

        errors = set_user_deleted(user)

        self.assertEqual(errors, [], "the delete reported a failure")
        row = _stored(i_user)
        # `active` is what the OpenIMISModel family reads, `validity_to` what
        # the rows not yet moved to the history table still carry. While the
        # migration is in flight the delete writes both.
        self.assertFalse(row["active"])
        self.assertIsNotNone(row["validity_to"])

    def test_a_deleted_user_drops_out_of_the_users_list(self):
        user = create_test_interactive_user(username="TestDeleteListed")
        # the clause resolve_users() builds to hide deleted users
        listed = Q(
            Q(i_user__isnull=True)
            | Q(*InteractiveUser.filter_validity(prefix="i_user__"))
        )
        self.assertTrue(User.objects.filter(listed, pk=user.pk).exists())

        set_user_deleted(user)

        self.assertFalse(
            User.objects.filter(listed, pk=user.pk).exists(),
            "deleted user is still listed in the Users searcher",
        )

    def test_filter_validity_reads_both_markers_and_honours_the_prefix(self):
        clauses = InteractiveUser.filter_validity(prefix="i_user__")
        rendered = " ".join(str(clause) for clause in clauses)
        self.assertIn("i_user__validity_to__isnull", rendered)
        self.assertIn("i_user__active", rendered)

    def test_deleting_a_technical_user_does_not_raise(self):
        # TechnicalUser has no delete_history of its own; the call used to
        # raise AttributeError, which set_user_deleted swallowed.
        user = create_test_technical_user(username="TestDeleteTechnical")

        errors = set_user_deleted(user)

        self.assertEqual(errors, [])
        self.assertIsNotNone(
            TechnicalUser.objects.filter(pk=user.t_user.pk)
            .values_list("validity_to", flat=True)
            .first()
        )

    def test_a_deleted_user_cannot_sign_in(self):
        # The list filter is not the whole of a delete: the credentials have
        # to stop working too.
        create_test_interactive_user(username="TestDeleteLogin", password="admin123")
        user = User.objects.get(username="TestDeleteLogin")
        backend = ModelBackend()
        self.assertIsNotNone(
            backend.authenticate(None, username="TestDeleteLogin", password="admin123")
        )

        set_user_deleted(user)

        self.assertIsNone(
            backend.authenticate(None, username="TestDeleteLogin", password="admin123"),
            "a deleted user can still sign in",
        )

    def test_user_row_itself_is_left_alone(self):
        # core_User carries no deletion marker, so its delete_history is an
        # intentional no-op: nothing to write, and no version to bump.
        user = create_test_interactive_user(username="TestDeleteUserRow")
        before = User.objects.filter(pk=user.pk).values_list(
            "username", flat=True
        ).first()

        user.delete_history()

        self.assertEqual(
            User.objects.filter(pk=user.pk).values_list("username", flat=True).first(),
            before,
        )
