import json
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    Throttled,
)
from django.test import RequestFactory, TestCase
from graphql.error import GraphQLError
from graphql.error.located_error import GraphQLLocatedError

from core.gql_errors import (
    BAD_REQUEST,
    RATE_LIMITED,
    CSRF_FAILED,
    FORBIDDEN,
    GENERIC_INTERNAL_MESSAGE,
    INTERNAL_ERROR,
    LOCKED_OUT,
    UNAUTHENTICATED,
    AuthenticationRequired,
    CodedGraphQLError,
    CsrfTokenInvalid,
    LockedOut,
    classify,
    error_code_for,
    format_error,
    safe_error_message,
)
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.schema import _check_csrf_token
from core.test_helpers import create_test_interactive_user


def resolver_error(exc):
    """What the executor hands the view for an exception raised in a resolver."""
    return GraphQLLocatedError(nodes=None, original_error=exc)


class ErrorCodeTest(TestCase):
    def test_declared_codes_are_used(self):
        cases = {
            AuthenticationRequired(): UNAUTHENTICATED,
            CsrfTokenInvalid("nope"): CSRF_FAILED,
            LockedOut("too many"): LOCKED_OUT,
        }
        for exc, expected in cases.items():
            with self.subTest(type(exc).__name__):
                self.assertEqual(expected, error_code_for(exc))
                self.assertEqual(expected, error_code_for(resolver_error(exc)))

    def test_codes_are_derived_for_framework_errors(self):
        cases = {
            PermissionDenied("no"): FORBIDDEN,
            ValidationError("bad"): BAD_REQUEST,
            GraphQLError("unknown field"): BAD_REQUEST,
            KeyError("csrftoken"): INTERNAL_ERROR,
            RuntimeError("boom"): INTERNAL_ERROR,
        }
        for exc, expected in cases.items():
            with self.subTest(type(exc).__name__):
                self.assertEqual(expected, error_code_for(resolver_error(exc)))

    def test_openimis_permission_error_convention_is_forbidden(self):
        # ~59 resolvers across modules signal authZ with the builtin.
        code, client_safe = classify(resolver_error(PermissionError("Unauthorized")))

        self.assertEqual(FORBIDDEN, code)
        self.assertTrue(client_safe)

    def test_real_filesystem_permission_error_is_internal(self):
        # Same class, but errno is set and the message carries a path.
        denied = PermissionError(13, "Permission denied")
        denied.filename = "/etc/shadow"

        code, client_safe = classify(resolver_error(denied))

        self.assertEqual(INTERNAL_ERROR, code)
        self.assertFalse(client_safe)

    def test_drf_exceptions_are_mapped(self):
        cases = {
            AuthenticationFailed("INCORRECT_CREDENTIALS"): UNAUTHENTICATED,
            NotAuthenticated(): UNAUTHENTICATED,
            Throttled(): RATE_LIMITED,
        }
        for exc, expected in cases.items():
            with self.subTest(type(exc).__name__):
                code, client_safe = classify(resolver_error(exc))
                self.assertEqual(expected, code)
                self.assertTrue(client_safe)

    def test_server_side_api_exception_is_internal(self):
        # A 5xx APIException is a server failure, so its detail is withheld.
        code, client_safe = classify(resolver_error(APIException("upstream blew up")))

        self.assertEqual(INTERNAL_ERROR, code)
        self.assertFalse(client_safe)

    def test_coded_graphql_error_defaults_to_internal(self):
        # CodedGraphQLError is for deliberate, client-facing failures that have
        # no more specific code yet; it must still carry one.
        self.assertEqual(
            INTERNAL_ERROR, error_code_for(CodedGraphQLError("could not generate"))
        )


class FormatErrorTest(TestCase):
    def test_every_error_carries_a_code(self):
        for exc in (AuthenticationRequired(), PermissionDenied("no"), RuntimeError("x")):
            with self.subTest(type(exc).__name__):
                formatted = format_error(resolver_error(exc), debug=True)
                self.assertIn("code", formatted["extensions"])

    def test_client_facing_messages_survive_in_production(self):
        formatted = format_error(
            resolver_error(CsrfTokenInvalid("CSRF token missing or incorrect.")),
            debug=False,
        )
        self.assertEqual("CSRF token missing or incorrect.", formatted["message"])
        self.assertEqual(CSRF_FAILED, formatted["extensions"]["code"])

    def test_unexpected_exception_is_not_disclosed_in_production(self):
        leaky = RuntimeError("db user=imis password=hunter2")

        formatted = format_error(resolver_error(leaky), debug=False)

        self.assertEqual(str(GENERIC_INTERNAL_MESSAGE), formatted["message"])
        self.assertNotIn("hunter2", json.dumps(formatted))
        self.assertEqual(INTERNAL_ERROR, formatted["extensions"]["code"])

    def test_unexpected_exception_is_readable_in_debug(self):
        formatted = format_error(resolver_error(RuntimeError("boom")), debug=True)

        self.assertEqual("boom", formatted["message"])
        self.assertEqual(INTERNAL_ERROR, formatted["extensions"]["code"])

    def test_login_failure_message_survives_in_production(self):
        formatted = format_error(
            resolver_error(AuthenticationFailed("INCORRECT_CREDENTIALS")), debug=False
        )

        self.assertEqual("INCORRECT_CREDENTIALS", formatted["message"])
        self.assertEqual(UNAUTHENTICATED, formatted["extensions"]["code"])

    def test_authorization_failure_message_survives_in_production(self):
        formatted = format_error(
            resolver_error(PermissionError("Unauthorized")), debug=False
        )

        self.assertEqual("Unauthorized", formatted["message"])
        self.assertEqual(FORBIDDEN, formatted["extensions"]["code"])

    def test_query_validation_errors_stay_readable_in_production(self):
        # These are feedback about the client's own query, not internals.
        formatted = format_error(GraphQLError('Cannot query field "nope"'), debug=False)

        self.assertEqual('Cannot query field "nope"', formatted["message"])
        self.assertEqual(BAD_REQUEST, formatted["extensions"]["code"])

    def test_locations_and_path_are_preserved(self):
        error = GraphQLLocatedError(
            nodes=None, original_error=PermissionDenied("no"), path=["createUser"]
        )

        self.assertEqual(["createUser"], format_error(error, debug=True)["path"])


class SafeErrorMessageTest(TestCase):
    def test_internal_detail_is_withheld_in_production(self):
        self.assertEqual(
            str(GENERIC_INTERNAL_MESSAGE),
            safe_error_message(RuntimeError("password=hunter2"), debug=False),
        )

    def test_client_facing_detail_is_kept_in_production(self):
        self.assertEqual(
            "no rights", safe_error_message(PermissionDenied("no rights"), debug=False)
        )

    def test_everything_is_kept_in_debug(self):
        self.assertEqual(
            "boom", safe_error_message(RuntimeError("boom"), debug=True)
        )


class CheckCsrfTokenTest(TestCase):
    def setUp(self):
        self.request = RequestFactory().post("/api/graphql")
        self.request.session = {}

    def enforced(self):
        """CSRF is skipped in dev and under the test runner; force it on."""
        patched = patch("core.schema.settings")
        settings = patched.start()
        self.addCleanup(patched.stop)
        settings.MODE = "prod"
        settings.IS_TESTING = False
        settings.USER_AGENT_CSRF_BYPASS = []
        return settings

    def test_missing_session_token_is_a_csrf_error_not_a_key_error(self):
        self.enforced()
        self.request.META["HTTP_X_CSRFTOKEN"] = "sent"

        with self.assertRaises(CsrfTokenInvalid):
            _check_csrf_token(self.request)

    def test_missing_request_header_is_a_csrf_error(self):
        self.enforced()
        self.request.session["csrftoken"] = "stored"

        with self.assertRaises(CsrfTokenInvalid):
            _check_csrf_token(self.request)

    def test_mismatched_token_is_a_csrf_error(self):
        self.enforced()
        self.request.session["csrftoken"] = "stored"
        self.request.META["HTTP_X_CSRFTOKEN"] = "other"

        with self.assertRaises(CsrfTokenInvalid):
            _check_csrf_token(self.request)

    def test_matching_token_passes(self):
        self.enforced()
        self.request.session["csrftoken"] = "same"
        self.request.META["HTTP_X_CSRFTOKEN"] = "same"

        _check_csrf_token(self.request)

    def test_every_csrf_failure_reports_the_same_code(self):
        self.enforced()
        self.request.META["HTTP_X_CSRFTOKEN"] = "sent"

        with self.assertRaises(CsrfTokenInvalid) as caught:
            _check_csrf_token(self.request)

        formatted = format_error(resolver_error(caught.exception), debug=False)
        self.assertEqual(CSRF_FAILED, formatted["extensions"]["code"])

    def test_dev_mode_still_skips_the_check(self):
        settings = self.enforced()
        settings.MODE = "dev"

        _check_csrf_token(self.request)


class GraphQLErrorResponseTest(openIMISGraphQLTestCase):
    """The codes must actually reach the wire, not just the formatter."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="gql_errors_user")

    def test_unauthenticated_query_reports_a_code_alongside_401(self):
        response = self.query("query { languages { name } }")

        self.assertEqual(401, response.status_code)
        errors = json.loads(response.content)["errors"]
        codes = [e.get("extensions", {}).get("code") for e in errors]
        self.assertIn(UNAUTHENTICATED, codes)

    def test_malformed_query_reports_a_code(self):
        response = self.query("query { thisFieldDoesNotExist }")

        errors = json.loads(response.content)["errors"]
        self.assertTrue(errors)
        for error in errors:
            self.assertIn("code", error.get("extensions", {}))
