from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from core.models import RightPermission
from core.rights_sync import (
    CONTENT_TYPE_MODEL,
    collect_declared_rights,
    right_id_for_permission_name,
    sync_right_permissions,
)


class RightsSyncTestCase(TestCase):
    def setUp(self):
        self.declared = collect_declared_rights()
        # Synchronise here, rather than assume the test database already is.
        #
        # `install()` calls `sync_right_permissions()` from core's `ready()`, but at
        # that point the runner has not switched to the test database yet: the
        # startup sync applies to the development database. The intended relay is
        # `rerun_after_migrate`, which `--keepdb` does not trigger since there is no
        # migration. Without this call, these tests therefore only passed when an
        # earlier test in the same run had itself synchronised - an order
        # dependency, invisible as long as no new right was declared, and which
        # showed up as soon as the modules were converted to `DJANGO_PERMS`.
        #
        # The invariant checked is indeed "after synchronisation, everything
        # declared is mapped", not "the database happens to be up to date".
        sync_right_permissions()

    # --- the mapping ------------------------------------------------------
    def test_every_declared_action_is_mapped(self):
        mapped = {
            (app, codename)
            for app, codename in RightPermission.objects.values_list(
                "permission__content_type__app_label", "permission__codename"
            )
        }
        missing = sorted(
            f"{app}.{codename}"
            for app, codename, _, _, _ in self.declared
            if (app, codename) not in mapped
        )
        self.assertEqual(missing, [])

    def test_the_mapping_points_at_the_declared_right(self):
        for app, codename, right_id, _, _ in self.declared[:30]:
            with self.subTest(name=f"{app}.{codename}"):
                self.assertEqual(
                    right_id_for_permission_name(f"{app}.{codename}"), right_id
                )

    # --- do not duplicate -------------------------------------------------
    def test_a_django_model_permission_is_reused_not_duplicated(self):
        """
        `claim.view_claim` already exists, created by django for the Claim model:
        that row is the one that must carry the mapping, not a copy under our own
        ContentType.
        """
        mapping = RightPermission.objects.select_related(
            "permission__content_type"
        ).get(permission__codename="view_claim", permission__content_type__app_label="claim")
        self.assertEqual(mapping.permission.content_type.model, "claim")
        self.assertEqual(mapping.right_id, 111001)

    def test_only_business_actions_get_a_synthetic_row(self):
        """
        Django only generates add/change/delete/view. So anything under our own
        ContentType has to be an action it does not know about.
        """
        crud = {"view", "add", "change", "delete"}
        for perm in Permission.objects.filter(
            content_type__model=CONTENT_TYPE_MODEL
        ).select_related("content_type"):
            verb = perm.codename.split("_")[0]
            if verb not in crud:
                continue
            # a synthetic CRUD verb is only admissible when django has no
            # permission of the same name
            with self.subTest(perm=f"{perm.content_type.app_label}.{perm.codename}"):
                self.assertFalse(
                    Permission.objects.filter(
                        content_type__app_label=perm.content_type.app_label,
                        codename=perm.codename,
                    )
                    .exclude(content_type__model=CONTENT_TYPE_MODEL)
                    .exists(),
                    "a django permission of the same name exists: it should have been reused",
                )

    # --- several permissions, one right -----------------------------------
    def test_several_permissions_may_share_one_right(self):
        """
        This is what allows naming every action without renumbering the roles.
        """
        shared = RightPermission.objects.filter(right_id=111010).select_related(
            "permission"
        )
        codenames = sorted(m.permission.codename for m in shared)
        self.assertIn("change_claim", codenames)
        self.assertIn("skip_claim_review", codenames)
        self.assertGreater(len(codenames), 2)
        for name in ("claim.change_claim", "claim.skip_claim_review"):
            self.assertEqual(right_id_for_permission_name(name), 111010)

    # --- idempotence and non-interference ---------------------------------
    def test_running_twice_changes_nothing(self):
        # `setUp` has already synchronised, so this reading really is the baseline
        # of a synchronised state. Taking it before any sync measured something
        # else: on a database where a right had just been declared, the first sync
        # legitimately created rows and the test failed with no idempotence defect
        # at all.
        before = (Permission.objects.count(), RightPermission.objects.count())
        sync_right_permissions()
        sync_right_permissions()
        self.assertEqual(
            (Permission.objects.count(), RightPermission.objects.count()), before
        )

    def test_permissions_we_did_not_create_are_left_alone(self):
        """Grievance's generated rights live under Ticket's ContentType."""
        theirs = Permission.objects.filter(id__in=[127100, 127102]).exclude(
            content_type__model=CONTENT_TYPE_MODEL
        )
        before = {p.id: (p.codename, p.content_type_id) for p in theirs}
        self.assertTrue(before)
        sync_right_permissions()
        after = {
            p.id: (p.codename, p.content_type_id)
            for p in Permission.objects.filter(id__in=list(before))
        }
        self.assertEqual(before, after)

    def test_a_grant_is_transferred_before_the_row_is_removed(self):
        """
        Deleting a granted permission would silently withdraw access. An obsolete
        but granted row must have its grant moved over to the permission taking
        over.
        """
        content_type, _ = ContentType.objects.get_or_create(
            app_label="claim", model=CONTENT_TYPE_MODEL
        )
        obsolete = Permission.objects.create(
            codename="view_claim", name="duplicate", content_type=content_type
        )
        group = Group.objects.create(name="transfer_test_group")
        group.permissions.add(obsolete)

        sync_right_permissions()

        self.assertFalse(Permission.objects.filter(id=obsolete.id).exists())
        survivors = {p.id for p in group.permissions.all()}
        real = Permission.objects.get(
            content_type__app_label="claim",
            content_type__model="claim",
            codename="view_claim",
        )
        self.assertIn(real.id, survivors)


class PermissionNameBridgeTestCase(TestCase):
    """
    The bridge: the roles carry integers, the code can write a django name.
    """

    def setUp(self):
        from core.test_helpers import create_right_only_user

        self.user = create_right_only_user("bridge_user", ["gql_query_claims_perms"])

    def test_has_perm_accepts_the_id_and_the_name(self):
        self.assertTrue(self.user.has_perm("111001"))
        self.assertTrue(self.user.has_perm("claim.view_claim"))

    def test_an_alias_name_resolves_to_the_same_right(self):
        """A user holding 111010 holds it under each of its names."""
        from core.test_helpers import create_right_only_user

        editor = create_right_only_user("bridge_editor", ["gql_mutation_update_claims_perms"])
        self.assertTrue(editor.has_perm("claim.change_claim"))
        self.assertTrue(editor.has_perm("claim.skip_claim_review"))

    def test_a_right_not_held_is_refused_under_both_forms(self):
        self.assertFalse(self.user.has_perm("111004"))
        self.assertFalse(self.user.has_perm("claim.delete_claim"))

    def test_an_unknown_name_resolves_to_nothing(self):
        self.assertIsNone(right_id_for_permission_name("claim.not_a_right"))
        self.assertIsNone(right_id_for_permission_name("without_a_dot"))
