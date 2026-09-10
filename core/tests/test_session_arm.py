from calendar import timegm
from datetime import datetime
from secrets import token_hex

from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, get_user
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.auth import revocation
from core.models import InteractiveUser, User, UserRole
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.services import open_admin_session, sign_out_everywhere, user_authentication
from core.test_helpers import (
    create_test_interactive_user,
    create_test_role,
    create_test_technical_user,
)

# force_login otherwise picks the first backend exposing get_user, which here is
# not the one login() uses - AxesStandaloneBackend has none.
MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


def _now():
    return timegm(datetime.utcnow().utctimetuple())


def _set_not_before(user, value):
    """A plain UPDATE, so the object cache cannot serve a stale row to the next
    request. Same shape as test_auth_revocation._set_not_before.
    """
    json_ext = dict(user.i_user.json_ext or {})
    json_ext[revocation.NOT_BEFORE_KEY] = value
    InteractiveUser.objects.all().filter(pk=user.i_user.pk).update(json_ext=json_ext)


def _password():
    """Generated, so no password-shaped literal ends up in the repository."""
    return token_hex(16) + "Aa1!"


def _request():
    """A request with a real, empty session - what `login()` needs."""
    request = RequestFactory().post("/api/graphql")
    SessionMiddleware(lambda r: None).process_request(request)
    return request


class OpenAdminSessionTest(TestCase):
    """`user_authentication` verifies a password. A session opened there exists
    before any second factor has been presented, and a session authenticates the
    API on its own - so the two steps have to be separable.
    """

    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.user = create_test_interactive_user(
            username="sessionArmStaff", password=cls.password
        )

    def test_authenticating_a_staff_user_opens_no_session(self):
        request = _request()

        user = user_authentication(request, self.user.username, self.password)

        # Asserted, not assumed: the session arm is gated on is_staff, so a
        # non-staff user would make this test pass for the wrong reason.
        self.assertTrue(user.is_staff)
        self.assertNotIn(SESSION_KEY, request.session)

    def test_open_admin_session_opens_one_for_a_staff_user(self):
        request = _request()
        user = user_authentication(request, self.user.username, self.password)

        self.assertTrue(open_admin_session(request, user))

        self.assertEqual(str(request.session[SESSION_KEY]), str(user.id))


class GraphQLSessionArmTest(openIMISGraphQLTestCase):
    """OP-3128 finding 9's table, in reverse. `languages` is the probe because
    resolve_languages raises AuthenticationRequired, which the view maps to 401.
    """

    PROBE = "query { languages { name } }"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(
            username="sessionArmGql", password=_password()
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user, backend=MODEL_BACKEND)

    def test_a_session_alone_is_refused(self):
        response = self.query(self.PROBE)

        self.assertEqual(response.status_code, 401)

    def test_a_revoked_token_is_refused_even_next_to_a_session(self):
        # The row from the ticket's table, end to end. It does not isolate this
        # middleware: moving the not-before also invalidates the session hash, so
        # it passes with the middleware reverted. The garbage-token test below is
        # the one that pins the middleware.
        token = BaseTestContext(user=self.user).get_jwt()
        # 60s ahead, not now: assert_not_revoked rejects on issued_at < not_before,
        # and the token's iat is the current second.
        _set_not_before(self.user, _now() + 60)

        response = self.query(
            self.PROBE, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
        )

        self.assertEqual(response.status_code, 401)

    def test_an_unusable_token_is_refused_rather_than_ignored(self):
        # Isolates the middleware from the session hash: the token is rejected
        # for a reason unrelated to any revocation, so the session stays valid.
        # Without the middleware the session out-ranks the token and this is a
        # 200; with it, the token is decoded and refused.
        self.client.cookies["JWT"] = "not-a-token"

        response = self.query(self.PROBE)

        self.assertEqual(response.status_code, 401)

    def test_a_valid_token_still_authenticates_next_to_a_session(self):
        token = BaseTestContext(user=self.user).get_jwt()

        response = self.query(
            self.PROBE, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
        )

        self.assertResponseNoErrors(response)


class SessionAuthHashTest(TestCase):
    """`django.contrib.auth.get_user` compares this hash on every
    session-authenticated request and flushes the session when it differs, so it
    is the one point where a revocation can reach the session arm.
    """

    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.user = create_test_interactive_user(
            username="sessionArmHash", password=cls.password
        )

    def test_a_password_change_changes_the_hash(self):
        before = self.user.get_session_auth_hash()

        self.user.i_user.set_password(_password())
        self.user.i_user.save()

        self.assertNotEqual(before, self.user.get_session_auth_hash())

    def test_signing_out_everywhere_changes_the_hash(self):
        # Backdated first: the not-before is epoch seconds and creating the user
        # already stamped one, so a sign-out inside that same second writes the
        # identical value and would prove nothing either way.
        _set_not_before(self.user, _now() - 60)
        user = User.objects.get(username=self.user.username)
        before = user.get_session_auth_hash()

        sign_out_everywhere(user)

        self.assertNotEqual(before, user.get_session_auth_hash())

    def test_a_role_change_leaves_the_hash_alone(self):
        before = self.user.get_session_auth_hash()

        UserRole.objects.create(
            user=self.user.i_user, role=create_test_role(), audit_user_id=-1
        )

        self.assertEqual(before, self.user.get_session_auth_hash())

    def test_a_technical_user_hash_follows_its_password(self):
        # Returns the core User bound to the new TechnicalUser, not the
        # TechnicalUser itself. A technical user has no i_user, so the password
        # is the only component of its hash that can move.
        technical = create_test_technical_user(
            username="sessionArmTech", password=_password(), staff=True
        )
        before = technical.get_session_auth_hash()

        technical.t_user.set_password(_password())
        technical.t_user.save()

        self.assertNotEqual(before, User.objects.get(
            username="sessionArmTech").get_session_auth_hash())


class RevokedSessionTest(TestCase):
    """The request path, not just the hash value. `get_user` is what every
    session-authenticated request goes through, and it consults
    `get_session_auth_fallback_hash` on a mismatch - a state that was
    unreachable while the hash came from the username, and so untested.
    """

    @classmethod
    def setUpTestData(cls):
        cls.password = _password()
        cls.user = create_test_interactive_user(
            username="sessionArmRevoked", password=cls.password
        )

    def test_a_session_authenticates_until_the_user_is_revoked(self):
        request = _request()
        self.assertTrue(open_admin_session(request, self.user))
        self.assertEqual(get_user(request).username, self.user.username)

        _set_not_before(self.user, _now() + 60)

        self.assertTrue(get_user(request).is_anonymous)

    # Rendering an admin page needs collected staticfiles under whitenoise's
    # manifest storage; nothing here is about static assets.
    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_the_admin_site_refuses_a_revoked_session(self):
        self.client.force_login(self.user, backend=MODEL_BACKEND)
        admin_index = reverse("admin:index")
        self.assertEqual(self.client.get(admin_index).status_code, 200)

        _set_not_before(self.user, _now() + 60)

        response = self.client.get(admin_index)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])


class SessionAuthFallbackHashTest(TestCase):
    """`SECRET_KEY_FALLBACKS` is empty in this deployment, so without these two
    the generator could be `return iter(())` and the suite would not notice.
    `get_user` reads it on every mismatch, which is why it has to exist at all.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(
            username="sessionArmFallback", password=_password()
        )

    def _session_request(self):
        request = _request()
        open_admin_session(request, self.user)
        return request

    def test_a_session_minted_under_a_rotated_key_is_still_accepted(self):
        request = self._session_request()
        retired_key = settings.SECRET_KEY

        with override_settings(
            SECRET_KEY="op3146-rotated", SECRET_KEY_FALLBACKS=[retired_key]
        ):
            self.assertEqual(get_user(request).username, self.user.username)
            # Re-stamped under the current key, so the next request verifies
            # without the fallback.
            self.assertEqual(
                request.session[HASH_SESSION_KEY], self.user.get_session_auth_hash()
            )

    def test_the_same_session_is_refused_when_the_old_key_is_not_a_fallback(self):
        request = self._session_request()

        with override_settings(SECRET_KEY="op3146-rotated", SECRET_KEY_FALLBACKS=[]):
            self.assertTrue(get_user(request).is_anonymous)
