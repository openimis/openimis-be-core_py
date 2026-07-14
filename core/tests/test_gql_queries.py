from django.test import TestCase

from core.gql.max_length_constraints import build_max_length_constraints

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