from django.test import TestCase

from core.models import InteractiveUser, Officer


class IdForAuditRegressionTestCase(TestCase):
    """Regression tests for id_for_audit returning Python's built-in `id`
    function instead of the record id.

    Any service stamping audit_user_id from these models crashed with
    ValidationError: "<built-in function id>" value must be an integer
    (e.g. contribution.services.create_premium)."""

    def test_interactive_user_id_for_audit_is_the_record_id(self):
        user = InteractiveUser(id=42)
        self.assertEqual(user.id_for_audit, 42)
        self.assertNotEqual(user.id_for_audit, id)

    def test_officer_id_for_audit_is_the_record_id(self):
        officer = Officer(id=7)
        self.assertEqual(officer.id_for_audit, 7)
        self.assertNotEqual(officer.id_for_audit, id)
