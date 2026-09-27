from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from core.test_helpers import create_right_only_user
from core.views import UserViewSet


class UserApiRightsTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.nobody = create_right_only_user("api_rights_nobody", [])
        self.reader = create_right_only_user(
            "api_rights_reader", ["gql_query_users_perms"]
        )

    def _call(self, user, method, action, **kwargs):
        request = getattr(self.factory, method)("/api/core/users/", **kwargs)
        force_authenticate(request, user=user)
        view = UserViewSet.as_view({method: action})
        return view(request, **({"pk": str(user.id)} if "pk" in action or kwargs.get("_pk") else {}))

    # --- reading ----------------------------------------------------------
    def test_listing_accounts_requires_the_query_right(self):
        request = self.factory.get("/api/core/users/")
        force_authenticate(request, user=self.nobody)
        response = UserViewSet.as_view({"get": "list"})(request)
        self.assertEqual(response.status_code, 403, response.data)

    def test_listing_accounts_is_allowed_with_the_query_right(self):
        request = self.factory.get("/api/core/users/")
        force_authenticate(request, user=self.reader)
        response = UserViewSet.as_view({"get": "list"})(request)
        self.assertEqual(response.status_code, 200)

    # --- the escalation ---------------------------------------------------
    def test_a_user_cannot_promote_itself(self):
        """The heart of the problem: PATCH is_superuser on one's own row."""
        request = self.factory.patch(
            f"/api/core/users/{self.nobody.id}/", {"is_superuser": True}, format="json"
        )
        force_authenticate(request, user=self.nobody)
        response = UserViewSet.as_view({"patch": "partial_update"})(
            request, pk=str(self.nobody.id)
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.nobody.refresh_from_db()
        self.assertFalse(self.nobody.is_superuser)

    def test_is_superuser_stays_read_only_even_with_the_update_right(self):
        """
        Even when allowed to modify an account, one does not promote oneself
        through this API: `is_superuser` is a clearance state, not a profile field.
        """
        editor = create_right_only_user(
            "api_rights_editor",
            ["gql_query_users_perms", "gql_mutation_update_users_perms"],
        )
        # A real change alongside it, so as not to hit the model's refusal of empty
        # updates: that refusal is precisely what the API returns when
        # `is_superuser` is the only field supplied, proof that it is ignored.
        request = self.factory.patch(
            f"/api/core/users/{editor.id}/",
            {"username": "api_rights_editor2", "is_superuser": True},
            format="json",
        )
        force_authenticate(request, user=editor)
        response = UserViewSet.as_view({"patch": "partial_update"})(
            request, pk=str(editor.id)
        )
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        editor.refresh_from_db()
        self.assertEqual(
            editor.username, "api_rights_editor2", "the editable field did change"
        )
        self.assertFalse(
            editor.is_superuser, "is_superuser must not be writable through the API"
        )

    # --- current_user stays open ------------------------------------------
    def test_current_user_stays_open_to_any_authenticated_account(self):
        request = self.factory.get("/api/core/users/current_user/")
        force_authenticate(request, user=self.nobody)
        response = UserViewSet.as_view({"get": "current_user"})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], self.nobody.username)
