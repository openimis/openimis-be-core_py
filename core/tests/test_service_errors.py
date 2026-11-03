import json
import traceback

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.access import authentication_error, permission_error
from core.gql_errors import (
    BAD_REQUEST,
    FORBIDDEN,
    GENERIC_INTERNAL_MESSAGE,
    INTERNAL_ERROR,
    UNAUTHENTICATED,
    format_error,
)
from core.service_errors import ServiceError, ServiceErrorException
from core.services.utils import output_exception


def failing_call():
    raise RuntimeError("db exploded")


class LegacyPayloadCompatibilityTest(TestCase):
    """The wire shape must not change: only `code` is added."""

    def test_output_exception_payload_is_byte_identical(self):
        # Exact equality, as the module test suites assert it: no added keys.
        self.assertDictEqual(
            {
                "success": False,
                "message": "Failed to create Contract",
                "detail": "nope",
                "data": "",
            },
            output_exception("Contract", "create", ValueError("nope")),
        )

    def test_output_exception_serialises_to_the_same_json(self):
        payload = output_exception("Contract", "create", ValueError("nope"))

        self.assertNotIn("code", json.loads(json.dumps(payload)))

    def test_the_code_rides_alongside_the_payload(self):
        cases = {
            PermissionDenied("no rights"): FORBIDDEN,
            ValidationError("bad field"): BAD_REQUEST,
            RuntimeError("db exploded"): INTERNAL_ERROR,
        }
        for exc, expected in cases.items():
            with self.subTest(type(exc).__name__):
                payload = output_exception("Contract", "create", exc)

                self.assertEqual(expected, payload.error.code)
                self.assertEqual(expected, ServiceError.from_dict(payload).code)

    def test_the_code_can_be_emitted_as_a_key_on_request(self):
        error = ServiceError(code=FORBIDDEN, message="no rights")

        self.assertEqual(FORBIDDEN, error.as_dict(with_code=True)["code"])
        self.assertNotIn("code", error.as_dict())

    def test_detail_still_carries_domain_messages_verbatim(self):
        # Modules put deliberate domain text here; sanitising it wholesale would
        # swallow real information. Narrowing this needs typed module errors.
        payload = output_exception(
            "Contract", "update", ValueError("ContractUpdateError: cannot update")
        )

        self.assertEqual("ContractUpdateError: cannot update", payload["detail"])

    def test_access_helpers_keep_their_three_key_shape(self):
        # These payloads have never carried a "data" key.
        self.assertDictEqual(
            {
                "success": False,
                "message": "Authentication required",
                "detail": "PermissionDenied",
            },
            authentication_error(),
        )

    def test_access_helpers_report_codes_alongside(self):
        self.assertEqual(UNAUTHENTICATED, authentication_error().error.code)
        self.assertEqual(FORBIDDEN, permission_error().error.code)

    def test_access_helpers_hand_out_fresh_dicts(self):
        first = permission_error()
        first["message"] = "mutated"

        self.assertEqual("Permissions required", permission_error()["message"])


class ServiceErrorValidationTest(TestCase):
    def test_code_must_come_from_the_vocabulary(self):
        with self.assertRaises(ValueError):
            ServiceError(code="NOT_A_CODE", message="x")

    def test_message_is_required(self):
        for bad in (None, "", "   "):
            with self.subTest(repr(bad)):
                with self.assertRaises(ValueError):
                    ServiceError(code=FORBIDDEN, message=bad)

    def test_exception_field_rejects_non_exceptions(self):
        with self.assertRaises(TypeError):
            ServiceError(code=FORBIDDEN, message="x", exception="boom")

    def test_field_errors_are_normalised_and_immutable(self):
        error = ServiceError(
            code=BAD_REQUEST, message="invalid", field_errors={"code": "required"}
        )

        self.assertEqual(("required",), error.field_errors["code"])
        with self.assertRaises(TypeError):
            error.field_errors["other"] = ("x",)

    def test_field_errors_reject_a_non_mapping(self):
        with self.assertRaises(TypeError):
            ServiceError(code=BAD_REQUEST, message="x", field_errors=["nope"])


class RetainedExceptionTest(TestCase):
    """The originating exception is kept so a caller can propagate it intact."""

    def build(self):
        try:
            failing_call()
        except RuntimeError as exc:
            return ServiceError.from_exception(exc, message="Failed to create Contract")

    def test_from_exception_retains_the_exception(self):
        error = self.build()

        self.assertIsInstance(error.exception, RuntimeError)

    def test_the_exception_is_not_serialised(self):
        self.assertNotIn("exception", self.build().as_dict())

    def test_equality_ignores_the_exception(self):
        left = ServiceError(code=FORBIDDEN, message="no", exception=ValueError("a"))
        right = ServiceError(code=FORBIDDEN, message="no", exception=KeyError("b"))

        self.assertEqual(left, right)

    def test_repr_does_not_dump_the_exception(self):
        # detail belongs in the repr; the exception object (and its traceback)
        # does not.
        rendered = repr(self.build())

        self.assertNotIn("exception=", rendered)
        self.assertNotIn("RuntimeError", rendered)

    def test_reraise_raises_the_original_object(self):
        error = self.build()

        with self.assertRaises(RuntimeError) as caught:
            error.reraise()

        self.assertIs(error.exception, caught.exception)

    def test_reraise_preserves_the_original_traceback(self):
        # Not assertRaises: it stores the exception with_traceback(None) to
        # avoid reference cycles, which would erase what this test checks.
        frames = []
        try:
            self.build().reraise()
        except RuntimeError as again:
            frames = traceback.extract_tb(again.__traceback__)

        self.assertIn("failing_call", [frame.name for frame in frames])


class ReraiseWithoutOriginalTest(TestCase):
    """A payload rebuilt from a dict has no exception left to re-raise."""

    def test_from_dict_does_not_recover_an_exception(self):
        rebuilt = ServiceError.from_dict(self_payload())

        self.assertIsNone(rebuilt.exception)

    def test_reraise_falls_back_to_a_carrying_exception(self):
        rebuilt = ServiceError.from_dict(self_payload())

        with self.assertRaises(ServiceErrorException) as caught:
            rebuilt.reraise()

        self.assertEqual(INTERNAL_ERROR, caught.exception.extensions["code"])
        self.assertEqual(rebuilt, caught.exception.error)

    def test_internal_payloads_are_not_disclosed_when_reraised(self):
        raised = ServiceErrorException(
            ServiceError(code=INTERNAL_ERROR, message="db exploded")
        )

        formatted = format_error(raised, debug=False)

        self.assertEqual(str(GENERIC_INTERNAL_MESSAGE), formatted["message"])
        self.assertEqual(INTERNAL_ERROR, formatted["extensions"]["code"])

    def test_client_facing_payloads_keep_their_message_when_reraised(self):
        raised = ServiceErrorException(
            ServiceError(code=FORBIDDEN, message="Permissions required")
        )

        formatted = format_error(raised, debug=False)

        self.assertEqual("Permissions required", formatted["message"])
        self.assertEqual(FORBIDDEN, formatted["extensions"]["code"])


def self_payload():
    return {
        "success": False,
        "message": "Failed to create Contract",
        "detail": "db exploded",
        "data": "",
        "code": INTERNAL_ERROR,
    }


class FromDictTest(TestCase):
    def test_success_payloads_are_not_errors(self):
        self.assertIsNone(ServiceError.from_dict({"success": True, "data": {}}))
        self.assertFalse(ServiceError.is_error_payload({"success": True}))

    def test_error_payloads_are_recognised(self):
        self.assertTrue(ServiceError.is_error_payload(self_payload()))

    def test_non_mappings_are_ignored(self):
        for value in (None, "error", 42, []):
            with self.subTest(repr(value)):
                self.assertIsNone(ServiceError.from_dict(value))
                self.assertFalse(ServiceError.is_error_payload(value))

    def test_a_legacy_payload_without_a_code_becomes_internal(self):
        payload = {"success": False, "message": "Failed", "detail": "x"}

        self.assertEqual(INTERNAL_ERROR, ServiceError.from_dict(payload).code)

    def test_an_unknown_code_is_not_trusted(self):
        payload = {"success": False, "message": "Failed", "code": "MADE_UP"}

        self.assertEqual(INTERNAL_ERROR, ServiceError.from_dict(payload).code)

    def test_a_payload_with_no_message_still_parses(self):
        self.assertIsNotNone(ServiceError.from_dict({"success": False}))

    def test_from_dict_prefers_the_attached_error(self):
        error = ServiceError(code=BAD_REQUEST, message="invalid")

        self.assertIs(error, ServiceError.from_dict(error.as_dict()))

    def test_round_trip_through_plain_keys_preserves_the_payload(self):
        error = ServiceError(
            code=BAD_REQUEST,
            message="invalid",
            detail="code is required",
            field_errors={"code": ["required"]},
        )

        # dict() drops the attached error, so this exercises the parsing path.
        rebuilt = ServiceError.from_dict(dict(error.as_dict(with_code=True)))

        self.assertEqual(error, rebuilt)


class ToGraphQLErrorTest(TestCase):
    def test_code_and_field_errors_reach_the_extensions(self):
        error = ServiceError(
            code=BAD_REQUEST, message="invalid", field_errors={"code": ["required"]}
        )

        extensions = error.to_graphql_error().extensions

        self.assertEqual(BAD_REQUEST, extensions["code"])
        self.assertEqual({"code": ["required"]}, extensions["field_errors"])

    def test_the_message_is_the_graphql_message(self):
        error = ServiceError(code=FORBIDDEN, message="Permissions required")

        self.assertEqual("Permissions required", str(error.to_graphql_error()))
