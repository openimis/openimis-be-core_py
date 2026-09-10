from calendar import timegm
from datetime import datetime
from secrets import token_hex

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from core.auth import revocation
from core.models import InteractiveUser
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.services import open_admin_session, user_authentication
from core.test_helpers import create_test_interactive_user

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


class SessionIsNotOpenedByPasswordVerification(TestCase):
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


class SessionDoesNotAuthenticateGraphQL(openIMISGraphQLTestCase):
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
        token = BaseTestContext(user=self.user).get_jwt()
        # 60s ahead, not now: assert_not_revoked rejects on issued_at < not_before,
        # and the token's iat is the current second.
        _set_not_before(self.user, _now() + 60)

        response = self.query(
            self.PROBE, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
        )

        self.assertEqual(response.status_code, 401)

    def test_a_valid_token_still_authenticates_next_to_a_session(self):
        token = BaseTestContext(user=self.user).get_jwt()

        response = self.query(
            self.PROBE, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
        )

        self.assertResponseNoErrors(response)
