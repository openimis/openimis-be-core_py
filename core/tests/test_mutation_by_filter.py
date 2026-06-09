import json
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.core.cache import caches

from core.models import User
from core.gql_queries import UserGQLType
from core.gql.gql_mutations.mutation_by_filter import (
    mutation_on_queryset_from_filter,
)
from core.utils import set_current_user, clear_current_user, clear_history_context


def _make_async_mutate_spy():
    """Return a simple async_mutate replacement that records the data it receives."""
    calls = []

    def _spy(cls, user, **data):
        calls.append({"cls": cls, "user": user, "data": dict(data)})
        return "ok"

    return _spy, calls


class MutationOnQuerysetFromFilterTests(TestCase):
    """
    Tests for mutation_on_queryset_from_filter, with emphasis on how it interacts
    with Model.get_queryset (in particular User.get_queryset for location / business
    access restrictions) when no pre-built queryset is supplied in the data.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        clear_current_user()
        clear_history_context()

    def setUp(self):
        clear_current_user()
        clear_history_context()
        caches["default"].clear()
        super().setUp()

    def tearDown(self):
        clear_current_user()
        clear_history_context()
        caches["default"].clear()
        super().tearDown()

    # ------------------------------------------------------------------
    # Core requested scenario:
    # - Use the User class + UserGQLType
    # - Querying user is "from region A"
    # - There exist users in region A and users in other regions
    # - Without supplying an input 'queryset' in data, the decorator must
    #   produce a queryset that has already been filtered by User.get_queryset
    #   (so foreign-region users are excluded even if the additional_filters
    #   would have matched them).
    # ------------------------------------------------------------------
    def test_without_input_queryset_user_get_queryset_enforces_region_restriction(self):
        """
        When the decorator is used on User without a pre-supplied queryset,
        it must obtain the base via User.get_queryset(User.objects, the_user).
        Any location/region/business-access filtering implemented inside
        User.get_queryset must therefore be visible in the resulting
        data["queryset"] before (or after) the mutation's additional_filters
        are applied.
        """
        # Create a "querying user" who only has rights on his own region.
        querying_user = User.objects.create(username="regional_admin_reg1")

        # Create target users: some "in the same region", some "in other regions".
        # We use username convention for the test; the patched get_queryset below
        # will simulate the region check that a real User.get_queryset would do
        # once business access / location restrictions are wired (e.g. via the
        # user's linked i_user / officer / claim_admin location, or UserBusinessAccess).
        local_user1 = User.objects.create(username="reg1_local_user_one")
        local_user2 = User.objects.create(username="reg1_local_user_two")
        foreign_user1 = User.objects.create(username="reg2_foreign_user_one")
        foreign_user2 = User.objects.create(username="reg3_foreign_user_two")

        # Define which users the querying_user is allowed to see (his "region").
        allowed_for_querying_user = {local_user1.pk, local_user2.pk}

        def _region_aware_get_queryset(queryset, user):
            """
            Stand-in for the real User.get_queryset logic that will (on this branch)
            enforce that a user can only see/touch other users that belong to
            locations / business units he has access to.
            """
            if user is not None and getattr(user, "pk", None) == querying_user.pk:
                return queryset.filter(pk__in=allowed_for_querying_user)
            # For any other caller (or no user), be permissive in this test
            # (the real implementation would still apply anonymous / default rules).
            return queryset

        spy_mutate, calls = _make_async_mutate_spy()

        # Decorate a mutation that operates on Users via additional_filters.
        # We use a broad filter that would match *all* our test users if there
        # were no row security (username contains "user" or "local" or "foreign").
        decorated = mutation_on_queryset_from_filter(
            User, UserGQLType, query_filters_field="additional_filters"
        )(spy_mutate)

        # Call without 'uuids' and without providing a 'queryset' in data.
        # The additional_filters would, on an unrestricted base, return users
        # from multiple regions.
        filters = {"username_Icontains": "user"}  # matches local_* and foreign_*
        data = {"additional_filters": json.dumps(filters)}

        with patch.object(User, "get_queryset", _region_aware_get_queryset):
            result = decorated("SomeMutationClass", querying_user, **data)

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 1)
        received_data = calls[0]["data"]

        # The key contract: a queryset must have been placed under the default key.
        self.assertIn("queryset", received_data)
        final_qs = received_data["queryset"]

        # Materialize to verify the security restriction was applied by the
        # get_queryset step before (or in conjunction with) the filter step.
        final_pks = set(final_qs.values_list("pk", flat=True))

        # Only the "local region" users should be present.
        self.assertIn(local_user1.pk, final_pks)
        self.assertIn(local_user2.pk, final_pks)
        self.assertNotIn(foreign_user1.pk, final_pks)
        self.assertNotIn(foreign_user2.pk, final_pks)

        # Sanity: the additional_filters were still applied on the already-restricted base
        # (all surviving users have "user" in the username).
        for u in final_qs:
            self.assertIn("user", u.username.lower())

    # ------------------------------------------------------------------
    # Other scenarios (as requested / proposed)
    # ------------------------------------------------------------------
    def test_with_input_queryset_it_updates_it_without_calling_get_queryset(self):
        """
        If the caller already supplies a queryset under the configured key
        (e.g. a pre-scoped queryset obtained via business access rules or
        a prior get_queryset call), the decorator must *update* it with the
        mutation filter and must NOT replace the base by calling
        Model.get_queryset again.
        """
        pre_base = User.objects.filter(username__startswith="pre_")
        # We mark it so the test can detect if get_queryset was called on the model.
        pre_base._pre_scoped_marker = "from-business-access-layer"

        spy_mutate, calls = _make_async_mutate_spy()
        decorated = mutation_on_queryset_from_filter(
            User, UserGQLType, queryset_key="target_queryset"
        )(spy_mutate)

        # Provide the pre-built queryset; also provide a filter that would normally
        # require get_queryset if we were in the "no input qs" path.
        data = {
            "target_queryset": pre_base,
            "additional_filters": json.dumps({"username_Icontains": "pre_"}),
        }

        with patch.object(User, "get_queryset", wraps=User.get_queryset) as mock_gq:
            decorated("Cls", None, **data)

        # get_queryset should not have been invoked by the decorator for the base,
        # because an input queryset was supplied.
        # (It may be called indirectly by other things, but not as the "build base" step.)
        # We at least assert that the final queryset in data is derived from the pre one.
        received = calls[0]["data"]
        self.assertIn("target_queryset", received)
        # get_queryset should not have been invoked (we supplied a pre qs)
        self.assertEqual(mock_gq.call_count, 0)
        # The final qs must derive from the input pre_ one (contains its filter condition)
        self.assertIn("pre", str(received["target_queryset"].query))

    def test_uuids_present_skips_filter_and_queryset_logic_entirely(self):
        """
        If 'uuids' are already present, the decorator must be a no-op with
        respect to queryset construction / get_queryset / additional_filters.
        """
        spy_mutate, calls = _make_async_mutate_spy()
        decorated = mutation_on_queryset_from_filter(User, UserGQLType)(spy_mutate)

        data = {
            "uuids": ["11111111-1111-1111-1111-111111111111"],
            "additional_filters": json.dumps({"username": "anything"}),
            # no 'queryset' supplied; decorator must not inject one (no-op)
        }

        with patch.object(User, "get_queryset") as mock_gq:
            decorated("Cls", None, **data)

        mock_gq.assert_not_called()
        # The inner mutate still receives the original data (no 'queryset' key forced in).
        self.assertNotIn("queryset", calls[0]["data"])

    def test_user_argument_and_current_user_fallback(self):
        """
        The decorator must use the explicit 'user' passed to the wrapper when
        present; otherwise fall back to get_current_user() before calling
        the model's get_queryset.
        """
        explicit_user = User.objects.create(username="explicit_caller")
        fallback_user = User.objects.create(username="fallback_caller")
        set_current_user(fallback_user)

        received_users = []

        def capture_user(cls, user, **data):
            received_users.append(user)
            data["queryset"] = User.objects.none()
            return "ok"

        decorated = mutation_on_queryset_from_filter(User, UserGQLType)(capture_user)

        # Call with explicit user
        decorated("C", explicit_user, additional_filters=json.dumps({"id": 0}))
        # Call without user (should use the thread-local)
        decorated("C", None, additional_filters=json.dumps({"id": 0}))

        self.assertIs(received_users[0], explicit_user)
        self.assertIs(received_users[1], fallback_user)

    def test_with_explicit_filters_handlers(self):
        """
        explicit_filters_handlers must be honored when building the Q filter
        that is applied on top of the (get_queryset-provided or supplied) base.
        """
        spy, calls = _make_async_mutate_spy()
        handlers = {"special": "username__startswith"}
        decorated = mutation_on_queryset_from_filter(
            User, UserGQLType, explicit_filters_handlers=handlers
        )(spy)

        # The key "special" is not a native GQL filter field on UserGQLType;
        # thanks to the handler it should become username__startswith=...
        data = {"additional_filters": json.dumps({"special": "handler_"})}

        # Create a matching user so the final qs is non-empty after both get_queryset and the filter.
        User.objects.create(username="handler_test_user")

        # We still want get_queryset to be in the picture; use a permissive patch for this test.
        with patch.object(User, "get_queryset", side_effect=lambda qs, u: qs):
            decorated("C", None, **data)

        # We mainly assert no crash and that the inner received a queryset.
        self.assertIn("queryset", calls[0]["data"])


# -----------------------------------------------------------------------------
# Additional scenarios proposed for coverage (can be turned into real tests):
#
# 1. "Implied location restriction via the user's linked objects"
#    - Create a querying InteractiveUser / core User that is linked to an Officer
#      or ClaimAdmin that has a health_facility in a specific district/region.
#    - Create target users (or ClaimAdmins / Officers) in the allowed location and
#      in other locations.
#    - Do NOT patch; instead (once User.get_queryset or the relevant model's
#      get_queryset implements the location logic using LocationManager or
#      UserBusinessAccess) call the decorator for real and assert only the
#      in-region objects are present in the resulting queryset.
#    - This is the "with user and implied location restriction for get_queryset"
#      scenario.
#
# 2. VersionedModel + validity interaction
#    - Use a model that relies on filter_validity() (e.g. Officer, ClaimAdmin).
#    - Verify/document whether the no-input-qs path in the queryset decorator
#      relies on the model's get_queryset to also apply validity (some do via
#      filter_queryset inside get_queryset), in contrast to the uuids path which
#      always does an explicit filter_validity() first.
#
# 3. Pre-supplied queryset that is *further* restricted by get_queryset?
#    - Current semantics: if queryset key present, we only do .filter(q_filter).
#    - Decide / test whether in some flows you still want to intersect with
#      get_queryset(user) even when a base was supplied. (Probably not; the
#      supplied qs is already the caller's idea of the secured set.)
#
# 4. Empty result after security + filter
#    - A regional user + filters that would only match foreign users -> resulting
#      queryset must be empty (no leakage).
#
# 5. Business model variant
#    - Once a mutation_on_queryset_from_filter_business_model exists, add
#      equivalent tests for Contract-like entities (extended_filters, the special
#      validity + amount handling, id vs uuid, etc.).
#
# 6. Integration-style test inside a real async_mutate (e.g. a user update or
#    user-role assignment mutation) that uses the decorator on User, with a
#    regional admin, and verifies that the mutation cannot affect users outside
#    the admin's business access scope.
# -----------------------------------------------------------------------------
