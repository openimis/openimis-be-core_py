import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from core.apps import CoreConfig
from core.models import HistoryModel, User
from core.middleware import ClearUserContextMiddleware
from core.test_helpers import create_test_interactive_user
from core.utils import (
    IMPERSONATE_USER_META,
    INVALID_IMPERSONATION_TARGET,
    ImpersonationDenied,
    clear_current_user,
    clear_original_user,
    get_current_user,
    get_original_user,
    handle_impersonation,
    set_current_user,
    set_original_user,
)


def request_for(target_id=None):
    """A stand-in for the request/context handle_impersonation reads."""
    meta = {} if target_id is None else {IMPERSONATE_USER_META: str(target_id)}
    return SimpleNamespace(META=meta)


class ImpersonationTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="ImpSuperuser", password="S3cret!pass", email="imp@test.com"
        )
        self.target = create_test_interactive_user(username="ImpTarget")
        # create_test_interactive_user makes superusers by default.
        self.plain_user = create_test_interactive_user(
            username="ImpPlain", custom_props={"is_superuser": False}
        )
        self.addCleanup(clear_current_user)
        self.addCleanup(clear_original_user)

    # -- the .env -> settings.py -> core chain --------------------------------

    def test_core_config_flag_comes_from_settings(self):
        self.assertEqual(
            settings.IMPERSONATION_ENABLED, CoreConfig.impersonation_enabled
        )

    # -- no header -----------------------------------------------------------

    def test_without_header_the_authenticated_user_is_used(self):
        effective = handle_impersonation(request_for(), self.plain_user)

        self.assertEqual(self.plain_user, effective)
        self.assertEqual(self.plain_user, get_current_user())
        self.assertIsNone(get_original_user())

    def test_without_header_a_previous_impersonation_is_not_inherited(self):
        set_original_user(self.superuser)
        set_current_user(self.target)

        effective = handle_impersonation(request_for(), self.superuser)

        self.assertEqual(self.superuser, effective)
        self.assertEqual(self.superuser, get_current_user())
        self.assertIsNone(get_original_user())

    # -- enabled -------------------------------------------------------------

    @patch.object(CoreConfig, "impersonation_enabled", True)
    def test_superuser_impersonates_target(self):
        effective = handle_impersonation(
            request_for(self.target.id), self.superuser
        )

        self.assertEqual(self.target, effective)
        self.assertEqual(self.target, get_current_user())
        self.assertEqual(self.superuser, get_original_user())

    @patch.object(CoreConfig, "impersonation_enabled", True)
    def test_non_superuser_cannot_impersonate(self):
        with self.assertRaises(ImpersonationDenied):
            handle_impersonation(request_for(self.target.id), self.plain_user)

        self.assertIsNone(get_original_user())

    @patch.object(CoreConfig, "impersonation_enabled", True)
    def test_unknown_target_is_refused(self):
        with self.assertRaises(ImpersonationDenied):
            handle_impersonation(request_for(uuid.uuid4()), self.superuser)

    @patch.object(CoreConfig, "impersonation_enabled", True)
    def test_malformed_target_is_refused(self):
        with self.assertRaises(ImpersonationDenied):
            handle_impersonation(request_for("not-a-uuid"), self.superuser)

    @patch.object(CoreConfig, "impersonation_enabled", True)
    def test_non_interactive_target_is_refused(self):
        self.target.i_user = None
        self.target.save()

        with self.assertRaises(ImpersonationDenied):
            handle_impersonation(request_for(self.target.id), self.superuser)

    # -- disabled (the production default) -----------------------------------

    @patch.object(CoreConfig, "impersonation_enabled", False)
    def test_header_is_refused_when_impersonation_is_disabled(self):
        with self.assertRaises(ImpersonationDenied):
            handle_impersonation(request_for(self.target.id), self.superuser)

        self.assertIsNone(get_original_user())

    @patch.object(CoreConfig, "impersonation_enabled", False)
    def test_disabled_does_not_break_ordinary_requests(self):
        effective = handle_impersonation(request_for(), self.plain_user)

        self.assertEqual(self.plain_user, effective)
        self.assertEqual(self.plain_user, get_current_user())

    # -- the message the frontend matches on ---------------------------------

    @patch.object(CoreConfig, "impersonation_enabled", True)
    def test_every_refusal_carries_the_marker_the_frontend_matches(self):
        cases = {
            "non superuser": (request_for(self.target.id), self.plain_user),
            "unknown target": (request_for(uuid.uuid4()), self.superuser),
            "malformed target": (request_for("not-a-uuid"), self.superuser),
        }
        for label, (request, user) in cases.items():
            with self.subTest(label):
                with self.assertRaises(ImpersonationDenied) as caught:
                    handle_impersonation(request, user)
                # The frontend lowercases before matching this substring.
                self.assertIn(
                    INVALID_IMPERSONATION_TARGET.lower(),
                    str(caught.exception).lower(),
                )

    @patch.object(CoreConfig, "impersonation_enabled", False)
    def test_disabled_refusal_carries_the_marker_too(self):
        with self.assertRaises(ImpersonationDenied) as caught:
            handle_impersonation(request_for(self.target.id), self.superuser)

        self.assertIn(
            INVALID_IMPERSONATION_TARGET.lower(), str(caught.exception).lower()
        )

    # -- audit attribution ---------------------------------------------------

    @patch.object(CoreConfig, "impersonation_enabled", True)
    def test_audit_names_the_impersonator_not_the_impersonated_user(self):
        handle_impersonation(request_for(self.target.id), self.superuser)

        self.assertEqual(
            self.superuser, HistoryModel.get_user(SimpleNamespace(audit_user_id=None))
        )

    def test_audit_falls_back_to_the_passed_user_when_not_impersonating(self):
        handle_impersonation(request_for(), self.plain_user)

        self.assertEqual(
            self.plain_user,
            HistoryModel.get_user(
                SimpleNamespace(audit_user_id=None), user=self.plain_user
            ),
        )


class ClearUserContextMiddlewareTest(TestCase):
    def setUp(self):
        self.addCleanup(clear_current_user)
        self.addCleanup(clear_original_user)

    def test_context_left_by_a_previous_request_is_cleared(self):
        user = create_test_interactive_user(username="ImpLeftover")
        set_current_user(user)
        set_original_user(user)
        seen = {}

        def get_response(request):
            seen["current"] = get_current_user()
            seen["original"] = get_original_user()
            return "response"

        response = ClearUserContextMiddleware(get_response)(request_for())

        self.assertEqual("response", response)
        self.assertIsNone(seen["current"])
        self.assertIsNone(seen["original"])
