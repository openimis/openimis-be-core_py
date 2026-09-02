from django.test import TestCase

from core.gql.max_length_constraints import build_max_length_constraints
from core.models.openimis_graphql_test_case import (
    openIMISGraphQLTestCase,
    BaseTestContext,
)
from core.test_helpers import create_test_interactive_user

try:
    from insuree.models import Insuree
except ImportError:
    Insuree = None


class MaxLengthConstraintsTestCase(TestCase):
    def test_build_max_length_constraints_returns_supported_admin_user_fields(self):
        constraints = build_max_length_constraints()

        self.assertIn("admin", constraints)
        self.assertIn("user", constraints["admin"])
        self.assertEqual(
            constraints["admin"]["user"],
            {
                "username": 50,
                "lastName": 100,
                "otherNames": 100,
                "phone": 50,
                "email": 200,
            },
        )

    def test_build_max_length_constraints_excludes_uncontrolled_models(self):
        constraints = build_max_length_constraints()

        self.assertNotIn("logentry", constraints)
        self.assertNotIn("session", constraints)
        self.assertNotIn("historicalinteractiveuser", constraints)

    def test_build_max_length_constraints_returns_insuree_fields_when_available(self):
        if not Insuree:
            self.skipTest("Insuree module is not installed")

        constraints = build_max_length_constraints()

        self.assertIn("insuree", constraints)
        self.assertIn("insuree", constraints["insuree"])
        self.assertEqual(
            constraints["insuree"]["insuree"],
            {
                "uuid": 36,
                "chfId": 50,
                "lastName": 100,
                "otherNames": 100,
                "marital": 1,
                "passport": 25,
                "phone": 50,
                "email": 100,
                "currentAddress": 200,
                "geolocation": 250,
                "status": 2,
            },
        )


class ResolverAuthenticationStatusTests(openIMISGraphQLTestCase):
    """An authN failure in a query resolver must surface as HTTP 401, not 200, so
    the client can tell an expired session (log out) from an authZ failure.
    resolve_languages raises AuthenticationRequired, which the view maps to 401.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="resolver_authn_user")

    def _languages_query(self, token=None):
        headers = (
            {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        )
        return self.query("query { languages { name } }", headers=headers)

    def test_unauthenticated_query_returns_401(self):
        self.assertEqual(self._languages_query().status_code, 401)

    def test_authenticated_query_not_401(self):
        token = BaseTestContext(user=self.user).get_jwt()
        self.assertNotEqual(self._languages_query(token).status_code, 401)
