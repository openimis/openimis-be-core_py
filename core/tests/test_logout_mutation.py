import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase
from graphql_jwt.settings import jwt_settings

from core.test_helpers import create_test_interactive_user


class LogoutMutationTest(TestCase):
    """The logout mutation has to end the session on the server, not only in the browser.

    Regression cover for the case where an admin clicked Logout, the front end
    dropped the JWT cookie, and the Django session created by the staff login
    path still authenticated /core/users/current_user/ - silently logging them
    back in on the next page load.
    """

    LOGOUT = "mutation { logout { success } }"

    def setUp(self):
        self.user = create_test_interactive_user(username="logout_mutation_test")
        self.graphql_url = "/%sgraphql" % settings.SITE_ROOT()
        self.current_user_url = "/%score/users/current_user/" % settings.SITE_ROOT()

    def _logout(self):
        return self.client.post(
            self.graphql_url,
            data=json.dumps({"query": self.LOGOUT}),
            content_type="application/json",
        )

    def _login(self):
        self.client.force_login(
            self.user, backend="django.contrib.auth.backends.ModelBackend"
        )

    def test_logout_reports_success(self):
        response = self._logout()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("errors", body)
        self.assertTrue(body["data"]["logout"]["success"])

    def test_logout_destroys_the_django_session_record(self):
        self._login()
        session_key = self.client.session.session_key
        self.assertTrue(SessionStore().exists(session_key))

        self._logout()

        self.assertFalse(SessionStore().exists(session_key))

    def test_logout_leaves_the_rest_api_unauthenticated(self):
        self._login()
        self.assertEqual(self.client.get(self.current_user_url).status_code, 200)

        self._logout()

        self.assertIn(self.client.get(self.current_user_url).status_code, (401, 403))

    def test_logout_rotates_the_session_cookie_to_an_anonymous_session(self):
        self._login()
        logged_in_key = self.client.session.session_key

        response = self._logout()

        # CSRF_USE_SESSIONS makes CsrfViewMiddleware seed a fresh session with a
        # new secret once ours has been flushed, so the response still carries a
        # session cookie - it just must not be the authenticated one any more.
        new_key = response.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertNotEqual(new_key, logged_in_key)
        self.assertNotIn(SESSION_KEY, SessionStore(new_key).load())

    def test_logout_expires_the_jwt_cookies(self):
        response = self._logout()

        for name in (
            jwt_settings.JWT_COOKIE_NAME,
            jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME,
        ):
            self.assertIn(name, response.cookies)
            self.assertEqual(response.cookies[name].value, "")

    def test_logout_expires_the_jwt_cookies_even_without_a_session(self):
        """Anonymous callers still get the deletion headers; logout is idempotent."""
        response = self._logout()

        self.assertTrue(response.json()["data"]["logout"]["success"])
        self.assertEqual(response.cookies[jwt_settings.JWT_COOKIE_NAME].value, "")


class LogoutRefreshTokenRevocationTest(TestCase):
    """Long-running refresh tokens live in the database and must be revoked."""

    def setUp(self):
        from core.schema import LogoutMutation

        self.mutation = LogoutMutation
        self.request = type(
            "Request",
            (),
            {"COOKIES": {jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME: "a-token"}},
        )()

    def test_sliding_refresh_tokens_have_nothing_to_revoke(self):
        with patch.object(
            jwt_settings, "JWT_LONG_RUNNING_REFRESH_TOKEN", False
        ), patch("core.schema.get_refresh_token") as get_refresh_token:
            self.mutation._revoke_refresh_token(self.request)

        get_refresh_token.assert_not_called()

    def test_long_running_refresh_token_is_revoked(self):
        with patch.object(
            jwt_settings, "JWT_LONG_RUNNING_REFRESH_TOKEN", True
        ), patch("core.schema.get_refresh_token") as get_refresh_token:
            self.mutation._revoke_refresh_token(self.request)

        get_refresh_token.assert_called_once_with("a-token", self.request)
        get_refresh_token.return_value.revoke.assert_called_once_with(self.request)

    def test_an_unusable_refresh_token_does_not_break_the_logout(self):
        with patch.object(
            jwt_settings, "JWT_LONG_RUNNING_REFRESH_TOKEN", True
        ), patch(
            "core.schema.get_refresh_token", side_effect=Exception("invalid")
        ):
            self.mutation._revoke_refresh_token(self.request)
