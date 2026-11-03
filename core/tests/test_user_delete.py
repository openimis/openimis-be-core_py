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


class UserDeleteGuardTest(TestCase):
    """A delete that works needs something standing in its way (OP-1572).

    Until OP-3194 the mutation wrote nothing, so nothing had to. It does now,
    and an administrator deleting their own account locks the instance out of
    itself - which is how this was found.
    """

    def _superuser(self, username):
        return create_test_interactive_user(
            username=username, custom_props={"is_superuser": True}
        )

    @staticmethod
    def _delete(actor, *targets):
        from core.schema import DeleteUserMutation

        return DeleteUserMutation.async_mutate(
            actor, uuids=[str(t.id) for t in targets]
        )

    @staticmethod
    def _is_live(user):
        return (
            InteractiveUser.objects.filter(pk=user.i_user_id)
            .values_list("active", flat=True)
            .first()
        )

    def test_a_user_cannot_delete_themselves(self):
        actor = self._superuser("OP1572Self")
        self._superuser("OP1572Other")  # so only the self rule can fire

        errors = self._delete(actor, actor)

        self.assertTrue(errors, "the self-deletion was allowed")
        self.assertIn("cannot_delete_self", str(errors))
        self.assertTrue(self._is_live(actor), "the caller deleted themselves")

    def test_the_last_superuser_cannot_be_deleted(self):
        actor = self._superuser("OP1572LastActor")
        target = self._superuser("OP1572Last")
        # make `target` the only superuser left, including the caller
        User.objects.filter(is_superuser=True).exclude(id=target.id).update(
            is_superuser=False
        )
        actor.refresh_from_db()
        actor.is_superuser = True  # the caller still needs the right to try

        errors = self._delete(actor, target)

        self.assertTrue(errors, "the last superuser was deleted")
        self.assertIn("cannot_delete_last_superuser", str(errors))
        self.assertTrue(self._is_live(target))

    def test_a_superuser_goes_when_another_one_remains(self):
        actor = self._superuser("OP1572KeeperActor")
        target = self._superuser("OP1572Keeper")
        self._superuser("OP1572Spare")

        errors = self._delete(actor, target)

        self.assertEqual(errors, [], f"refused unexpectedly: {errors}")
        self.assertFalse(self._is_live(target))

    def test_an_ordinary_user_is_unaffected(self):
        actor = self._superuser("OP1572PlainActor")
        target = create_test_interactive_user(
            username="OP1572Plain", custom_props={"is_superuser": False}
        )

        errors = self._delete(actor, target)

        self.assertEqual(errors, [], f"refused unexpectedly: {errors}")
        self.assertFalse(self._is_live(target))

    def test_an_unknown_uuid_is_titled_with_that_uuid(self):
        """The loop used to rebind `user`, so the title held a User object.

        Two uuids, because a single error is collapsed to its `list` by the
        caller and the title would not be visible. The message itself still
        does not name the id - `"...id_does_not_exist" % {"id": ...}` has no
        placeholder to fill, which is what its `# noqa: F504` marks - and that
        is left alone here.
        """
        from core.schema import DeleteUserMutation

        actor = self._superuser("OP1572Unknown")
        missing = [
            "00000000-0000-0000-0000-00000000dead",
            "00000000-0000-0000-0000-00000000beef",
        ]

        errors = DeleteUserMutation.async_mutate(actor, uuids=missing)

        self.assertEqual([e["title"] for e in errors], missing)
