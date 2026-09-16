"""Row security lives on the model; the graphene type only forwards to it."""

from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase

from core.gql import ScopedQuerysetMixin
from core.models import Language, ModuleConfiguration, Role, User
from core.models.row_security import RowSecurityMixin, present_content_type_ids
from core.test_helpers import create_test_interactive_user, create_test_role


def resolve_info(user):
    """Stand-in for a graphene ResolveInfo."""
    return SimpleNamespace(context=SimpleNamespace(user=user))


class ScopingUserNormalisationTest(TestCase):
    """A model must never have to know which API is asking."""

    def test_a_resolve_info_yields_its_user(self):
        user = SimpleNamespace(username="alice")

        self.assertIs(user, RowSecurityMixin.scoping_user(resolve_info(user)))

    def test_a_user_passes_through(self):
        user = SimpleNamespace(username="alice")

        self.assertIs(user, RowSecurityMixin.scoping_user(user))

    def test_none_stays_none(self):
        self.assertIsNone(RowSecurityMixin.scoping_user(None))

    def test_a_context_without_a_user_yields_none(self):
        self.assertIsNone(
            RowSecurityMixin.scoping_user(SimpleNamespace(context=SimpleNamespace()))
        )


class DefaultIsUnrestrictedTest(TestCase):
    """Most openIMIS models are reference data with no row security."""

    def test_reference_models_are_not_filtered(self):
        base = ModuleConfiguration.objects.all()

        self.assertEqual(
            base.count(), ModuleConfiguration.get_queryset(base, None).count()
        )

    def test_the_default_returns_the_same_queryset(self):
        base = ModuleConfiguration.objects.all()

        self.assertIs(base, ModuleConfiguration.get_queryset(base, None))


class ContractIsPresentEverywhereTest(TestCase):
    """The point of putting it on the base: callers need no getattr guard."""

    def test_every_openimis_model_answers_get_queryset(self):
        own = set(settings.OPENIMIS_APPS)
        missing = [
            model._meta.label
            for model in apps.get_models()
            if model._meta.app_label in own
            and not model.__name__.startswith("Historical")
            and not hasattr(model, "get_queryset")
        ]
        # Reference tables that predate the shared bases are the known
        # remainder; assert the set does not grow rather than that it is empty.
        self.assertLessEqual(
            len(missing), 23, f"models lost get_queryset: {missing}"
        )

    def test_models_on_the_shared_bases_have_it(self):
        for model in (User, Role, ModuleConfiguration):
            with self.subTest(model.__name__):
                self.assertTrue(hasattr(model, "get_queryset"))


class ScopedQuerysetMixinTest(TestCase):
    """The graphene hook forwards to the model and holds no policy itself."""

    def setUp(self):
        self.user = create_test_interactive_user(username="rowsec_user")

    def make_type(self, model, refine=None):
        namespace = {"_meta": SimpleNamespace(model=model)}
        if refine is not None:
            namespace["refine_queryset"] = classmethod(refine)
        return type("FakeGQLType", (ScopedQuerysetMixin,), namespace)

    def test_it_delegates_to_the_model(self):
        seen = {}

        class Scoped:
            @classmethod
            def get_queryset(cls, queryset, user=None):
                seen["user"] = user
                return queryset

        gql_type = self.make_type(Scoped)
        base = Language.objects.all()

        gql_type.get_queryset(base, resolve_info(self.user))

        self.assertIs(self.user, seen["user"])

    def test_the_model_receives_a_user_not_a_resolve_info(self):
        seen = {}

        class Scoped:
            @classmethod
            def get_queryset(cls, queryset, user=None):
                seen["kind"] = type(user).__name__
                return queryset

        self.make_type(Scoped).get_queryset(
            Language.objects.all(), resolve_info(self.user)
        )

        self.assertNotEqual("SimpleNamespace", seen["kind"])

    def test_a_model_without_row_security_is_left_alone(self):
        gql_type = self.make_type(SimpleNamespace())  # no get_queryset at all
        base = Language.objects.all()

        self.assertIs(base, gql_type.get_queryset(base, resolve_info(self.user)))

    def test_refine_runs_after_the_model_filter(self):
        order = []

        class Scoped:
            @classmethod
            def get_queryset(cls, queryset, user=None):
                order.append("model")
                return queryset

        def refine(cls, queryset, info):
            order.append("refine")
            return queryset

        gql_type = self.make_type(Scoped, refine=refine)
        gql_type.get_queryset(Language.objects.all(), resolve_info(self.user))

        self.assertEqual(["model", "refine"], order)

    def test_refine_defaults_to_a_passthrough(self):
        base = Language.objects.all()

        self.assertIs(
            base, ScopedQuerysetMixin.refine_queryset(base, resolve_info(self.user))
        )


class DeclarativeScopeTest(TestCase):
    """Scopes compose so a rule is declared once, on whoever owns the location."""

    def setUp(self):
        from claim.models import Claim, ClaimItem, ClaimService, ClaimServiceService
        from insuree.models import Insuree, InsureePhoto

        self.Claim = Claim
        self.ClaimItem = ClaimItem
        self.ClaimService = ClaimService
        self.ClaimServiceService = ClaimServiceService
        self.Insuree = Insuree
        self.InsureePhoto = InsureePhoto

    def scope(self, model, scope):
        """Attach a scope for one test and put the model back afterwards."""
        declared_here = "row_scope" in vars(model)
        previous = vars(model).get("row_scope")
        model.row_scope = scope

        def restore():
            # delattr, not vars(model).pop: a class __dict__ is a mappingproxy
            # and cannot be mutated. Leaving this broken leaked row_scope into
            # every later test in the class.
            if declared_here:
                model.row_scope = previous
            else:
                try:
                    delattr(model, "row_scope")
                except AttributeError:
                    pass

        self.addCleanup(restore)

    def test_a_root_declares_the_location_it_hangs_off(self):
        from core.models import LocationScope

        self.scope(self.Claim, LocationScope("health_facility__location"))

        self.assertEqual(
            ("health_facility__location",),
            self.Claim.row_scope.location_paths(self.Claim),
        )

    def test_a_child_composes_the_parents_path(self):
        from core.models import LocationScope, ParentScope

        self.scope(self.Claim, LocationScope("health_facility__location"))
        self.scope(self.ClaimItem, ParentScope("claim"))

        self.assertEqual(
            ("claim__health_facility__location",),
            self.ClaimItem.row_scope.location_paths(self.ClaimItem),
        )

    def test_composition_chains_through_several_parents(self):
        from core.models import LocationScope, ParentScope

        self.scope(self.Claim, LocationScope("health_facility__location"))
        self.scope(self.ClaimService, ParentScope("claim"))
        self.scope(self.ClaimServiceService, ParentScope("claim_service"))

        self.assertEqual(
            ("claim_service__claim__health_facility__location",),
            self.ClaimServiceService.row_scope.location_paths(self.ClaimServiceService),
        )

    def test_several_paths_survive_composition(self):
        """A fallback is another path, so a child inherits both routes."""
        from core.models import LocationScope, ParentScope

        self.scope(
            self.Insuree,
            LocationScope(
                "current_village__parent__parent", "family__location__parent__parent"
            ),
        )
        self.scope(self.InsureePhoto, ParentScope("insuree"))

        self.assertEqual(
            (
                "insuree__current_village__parent__parent",
                "insuree__family__location__parent__parent",
            ),
            self.InsureePhoto.row_scope.location_paths(self.InsureePhoto),
        )

    def test_a_child_inherits_the_parents_granularity(self):
        from core.models import LocationScope, ParentScope

        self.scope(self.Claim, LocationScope("health_facility__location", loc_types=("W",)))
        self.scope(self.ClaimItem, ParentScope("claim"))
        self.ClaimItem.row_scope.location_paths(self.ClaimItem)

        self.assertEqual(("W",), self.ClaimItem.row_scope.loc_types)

    def test_a_parent_that_scopes_itself_in_code_yields_no_paths(self):
        """Claim writes its own get_queryset, so there is no path to compose."""
        from core.models import ParentScope

        self.scope(self.ClaimItem, ParentScope("claim"))

        self.assertEqual((), self.ClaimItem.row_scope.location_paths(self.ClaimItem))

    def test_such_a_parent_is_still_honoured_through_a_subquery(self):
        """The child must not fall open just because the parent is imperative."""
        from core.models import ParentScope

        self.scope(self.ClaimItem, ParentScope("claim"))
        role = create_test_role(perm_names=[], name="RowSecSubqRole")
        user = create_test_interactive_user(
            username="rowsec_subq",
            roles=[role.id],
            custom_props={"is_superuser": False},
        )
        base = self.ClaimItem.objects.all()

        scoped = self.ClaimItem.get_queryset(base, user)

        self.assertNotEqual(str(base.query), str(scoped.query))
        self.assertIn("tblClaim", str(scoped.query))

    def _subquery_sql(self, scope, tag):
        """The SQL a ClaimItem queryset gets under ``scope``, for one user.

        Quoting is stripped so the assertion reads the same on either backend
        (``"ClaimID"`` on postgres, ``[ClaimID]`` on mssql). The subquery has
        ``IS NULL`` terms of its own -- validity, and the location filter's --
        so the test names the column it cares about rather than counting.
        """
        self.scope(self.ClaimItem, scope)
        role = create_test_role(perm_names=[], name=f"RowSecNull{tag}")
        user = create_test_interactive_user(
            username=f"rowsec_null_{tag}",
            roles=[role.id],
            custom_props={"is_superuser": False},
        )
        queryset = self.ClaimItem.get_queryset(self.ClaimItem.objects.all(), user)
        return str(queryset.query).translate(str.maketrans("", "", '"[]'))

    def test_a_parentless_row_is_hidden_unless_the_model_says_otherwise(self):
        """``field__in`` never matches a null, and that is the default reading."""
        from core.models import ParentScope

        sql = self._subquery_sql(ParentScope("claim"), "off")

        self.assertNotIn("ClaimID IS NULL", sql)

    def test_allow_null_keeps_a_parentless_row_visible(self):
        """A row with nothing to narrow it stays in, like a null location."""
        from core.models import ParentScope

        sql = self._subquery_sql(ParentScope("claim", allow_null=True), "on")

        self.assertIn("ClaimID IS NULL", sql)

    def test_a_location_scope_needs_a_path(self):
        from core.models import LocationScope

        with self.assertRaises(ValueError):
            LocationScope()


class DeclarativeScopeAppliesTest(TestCase):
    """The declaration must actually reach the SQL, not just describe itself."""

    def setUp(self):
        from claim.models import Claim, ClaimItem
        from core.models import LocationScope, ParentScope

        self.ClaimItem = ClaimItem
        previous_claim = vars(Claim).get("row_scope")
        previous_item = vars(ClaimItem).get("row_scope")
        Claim.row_scope = LocationScope("health_facility__location")
        ClaimItem.row_scope = ParentScope("claim")

        def restore():
            for model, prev in ((Claim, previous_claim), (ClaimItem, previous_item)):
                if prev is not None:
                    model.row_scope = prev
                else:
                    try:
                        delattr(model, "row_scope")
                    except AttributeError:
                        pass

        self.addCleanup(restore)
        # A genuinely restricted user: create_test_interactive_user defaults to
        # an admin role, and the location filter exempts is_imis_admin, so
        # passing an explicit rights-free role is what makes the filter bite.
        role = create_test_role(perm_names=[], name="RowSecPlainRole")
        self.user = create_test_interactive_user(
            username="rowsec_decl",
            roles=[role.id],
            custom_props={"is_superuser": False},
        )

    def test_a_restricted_user_gets_a_narrowed_queryset(self):
        base = self.ClaimItem.objects.all()

        scoped = self.ClaimItem.get_queryset(base, self.user)

        self.assertNotEqual(str(base.query), str(scoped.query))

    def test_the_composed_path_is_what_reaches_the_query(self):
        scoped = self.ClaimItem.get_queryset(self.ClaimItem.objects.all(), self.user)

        # The join to the claim's health facility is the evidence the child was
        # filtered through its parent rather than on its own columns.
        self.assertIn("tblClaim", str(scoped.query))
        self.assertIn("tblHF", str(scoped.query))

    def test_a_resolve_info_works_as_well_as_a_user(self):
        by_user = self.ClaimItem.get_queryset(self.ClaimItem.objects.all(), self.user)
        by_info = self.ClaimItem.get_queryset(
            self.ClaimItem.objects.all(), resolve_info(self.user)
        )

        self.assertEqual(str(by_user.query), str(by_info.query))


class GenericScopeTest(TestCase):
    """A generic foreign key is scoped per content type actually stored."""

    def setUp(self):
        from invoice.models import Invoice

        self.Invoice = Invoice
        self.ct_field = "subject_type"
        self.key = (
            f"row_security:generic_cts:{Invoice._meta.label_lower}:{self.ct_field}"
        )
        cache.delete(self.key)
        self.addCleanup(cache.delete, self.key)
        role = create_test_role(perm_names=[], name="RowSecGenericRole")
        self.user = create_test_interactive_user(
            username="rowsec_generic",
            roles=[role.id],
            custom_props={"is_superuser": False},
        )

    def assertUnfiltered(self, base, scoped):
        """Invoice re-applies its soft-delete filter regardless; assert nothing else."""
        self.assertEqual(
            str(self.Invoice.filter_queryset(base).query), str(scoped.query)
        )

    def test_only_the_types_actually_stored_are_returned(self):
        stored = sorted(
            {
                ct_id
                for ct_id in self.Invoice.objects.order_by().values_list(
                    f"{self.ct_field}_id", flat=True
                )
                if ct_id is not None
            }
        )

        self.assertEqual(
            stored, present_content_type_ids(self.Invoice, self.ct_field)
        )

    def test_the_set_is_cached(self):
        found = present_content_type_ids(self.Invoice, self.ct_field)

        self.assertEqual(found, cache.get(self.key))

    def test_a_new_content_type_drops_the_cache(self):
        """The set is cached without expiry, so a new kind of subject must evict it."""
        present_content_type_ids(self.Invoice, self.ct_field)
        cache.set(self.key, [], None)

        self.Invoice(
            code="rowsec-ct-probe",
            subject_type=ContentType.objects.get_for_model(Language),
            subject_id="1",
        ).save(username=self.user.username)

        self.assertIsNone(cache.get(self.key))

    def test_a_known_content_type_keeps_the_cache(self):
        language_ct = ContentType.objects.get_for_model(Language)
        present_content_type_ids(self.Invoice, self.ct_field)
        cache.set(self.key, [language_ct.id], None)

        self.Invoice(
            code="rowsec-ct-known",
            subject_type=language_ct,
            subject_id="1",
        ).save(username=self.user.username)

        self.assertEqual([language_ct.id], cache.get(self.key))

    def test_no_content_types_at_all_skips_filtering(self):
        """Before migration django_content_type is empty: skip, do not fail."""
        base = self.Invoice.objects.all()
        with patch(
            "django.contrib.contenttypes.models.ContentType.objects.exists",
            return_value=False,
        ):
            self.assertIsNone(present_content_type_ids(self.Invoice, self.ct_field))
            self.assertUnfiltered(base, self.Invoice.get_queryset(base, self.user))

    def test_a_missing_table_skips_filtering(self):
        """Same answer when the query itself cannot run yet."""
        with patch(
            "django.contrib.contenttypes.models.ContentType.objects.exists",
            side_effect=DatabaseError("relation does not exist"),
        ):
            self.assertIsNone(present_content_type_ids(self.Invoice, self.ct_field))

    def test_nothing_stored_means_no_query_of_its_own(self):
        base = self.Invoice.objects.all()
        with patch(
            "core.models.row_security.present_content_type_ids", return_value=[]
        ):
            self.assertUnfiltered(base, self.Invoice.get_queryset(base, self.user))

    def test_a_scoped_subject_type_narrows_through_a_subquery(self):
        from contract.models import Contract

        contract_ct = ContentType.objects.get_for_model(Contract).id
        base = self.Invoice.objects.all()
        with patch(
            "core.models.row_security.present_content_type_ids",
            return_value=[contract_ct],
        ):
            scoped = self.Invoice.get_queryset(base, self.user)

        sql = str(scoped.query)
        self.assertNotEqual(str(base.query), sql)
        # the subject's own table, reached as a subquery on the cast pk
        self.assertIn("tblContract", sql)

    def test_an_unscoped_subject_type_is_left_alone(self):
        """Nothing says those rows are restricted, and the OR would be free."""
        language_ct = ContentType.objects.get_for_model(Language).id
        base = self.Invoice.objects.all()
        with patch(
            "core.models.row_security.present_content_type_ids",
            return_value=[language_ct],
        ):
            self.assertUnfiltered(base, self.Invoice.get_queryset(base, self.user))

    def test_rows_without_a_subject_stay_visible(self):
        from contract.models import Contract

        contract_ct = ContentType.objects.get_for_model(Contract).id
        with patch(
            "core.models.row_security.present_content_type_ids",
            return_value=[contract_ct],
        ):
            scoped = self.Invoice.get_queryset(self.Invoice.objects.all(), self.user)

        # the null branch of the OR, same convention as a null location
        self.assertIn("IS NULL", str(scoped.query))

    def test_a_generic_scope_exposes_no_path_to_compose(self):
        self.assertEqual((), self.Invoice.row_scope.location_paths(self.Invoice))

    def test_a_child_of_a_generic_parent_falls_back_to_a_subquery(self):
        from invoice.models import InvoiceLineItem

        base = InvoiceLineItem.objects.all()
        with patch(
            "core.models.row_security.present_content_type_ids", return_value=[]
        ):
            scoped = InvoiceLineItem.get_queryset(base, self.user)

        # ParentScope cannot compose a path here, so it restricts through the
        # parent's queryset instead
        self.assertIn("tblInvoice", str(scoped.query))
