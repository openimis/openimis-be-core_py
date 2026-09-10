from secrets import token_hex

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from core.services import open_admin_session, user_authentication
from core.test_helpers import create_test_interactive_user


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
