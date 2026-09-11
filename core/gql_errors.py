"""openIMIS GraphQL error taxonomy.

Every error defined here carries a stable, unlocalised ``code`` in the GraphQL
``extensions`` alongside its human-readable ``message``. That split matters:
messages run through ``gettext`` (the ``en`` catalogue already rewrites
"unauthenticated" to "Authentication required", and an ``fr`` catalogue
exists), so a client that branches on message text breaks as soon as the
wording or the locale changes. Codes are what clients should match on.

graphql-core copies an ``extensions`` attribute off the original exception when
it wraps it in ``GraphQLLocatedError``, so the mixin below works for plain
exceptions too, not only ``GraphQLError`` subclasses.
"""

from django.conf import settings
from django.core.exceptions import (
    PermissionDenied as DjangoPermissionDenied,
    ValidationError as DjangoValidationError,
)
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError, format_error as format_graphql_core_error
from graphql_jwt.exceptions import JSONWebTokenError
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed as DRFAuthenticationFailed,
    NotAuthenticated,
    PermissionDenied as DRFPermissionDenied,
    Throttled,
)

# Stable error codes. Clients branch on these; never translate or reword them.
UNAUTHENTICATED = "UNAUTHENTICATED"
FORBIDDEN = "FORBIDDEN"
CSRF_FAILED = "CSRF_FAILED"
RATE_LIMITED = "RATE_LIMITED"
LOCKED_OUT = "LOCKED_OUT"
BAD_REQUEST = "BAD_REQUEST"
NOT_FOUND = "NOT_FOUND"
CONFLICT = "CONFLICT"
INTERNAL_ERROR = "INTERNAL_ERROR"

# The closed vocabulary. Anything reporting an openIMIS error -- GraphQL
# extensions, a service payload, a FHIR OperationOutcome -- draws its code from
# here, so one failure reads the same whichever API surfaced it.
ERROR_CODES = (
    UNAUTHENTICATED,
    FORBIDDEN,
    CSRF_FAILED,
    RATE_LIMITED,
    LOCKED_OUT,
    BAD_REQUEST,
    NOT_FOUND,
    CONFLICT,
    INTERNAL_ERROR,
)

# Substituted for an unexpected exception's message outside DEBUG, so internals
# (SQL, file paths, key names) do not reach the client. The real one is logged.
GENERIC_INTERNAL_MESSAGE = _(
    "An unexpected error occurred, please contact your administrator"
)


class CodedErrorMixin:
    """Attach ``error_code`` to the exception so it lands in ``extensions.code``."""

    error_code = INTERNAL_ERROR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        extensions = dict(getattr(self, "extensions", None) or {})
        extensions.setdefault("code", self.error_code)
        self.extensions = extensions


class AuthenticationRequired(CodedErrorMixin, JSONWebTokenError):
    # Subclassing JSONWebTokenError makes OpenIMISGraphQLView return 401; Django's
    # PermissionDenied stays 200. Distinct "unauthenticated" message separates
    # authN from the "unauthorized" authZ (has_perms) failures.
    default_message = _("unauthenticated")
    error_code = UNAUTHENTICATED


class CodedGraphQLError(CodedErrorMixin, GraphQLError):
    """A GraphQLError that clients can identify without reading the message."""


class CsrfTokenInvalid(CodedErrorMixin, DjangoPermissionDenied):
    """Raised when a mutation arrives without a usable CSRF token.

    Stays a Django PermissionDenied so the HTTP status (200, error in the body)
    does not change for existing clients; the code is what is new.
    """

    error_code = CSRF_FAILED


class LockedOut(CodedErrorMixin, GraphQLError):
    """Too many failed login attempts; the account is in its cool-off window."""

    error_code = LOCKED_OUT


def _root_error(error):
    """The exception the executor wrapped, or the error itself if unwrapped."""
    original = getattr(error, "original_error", None)
    return original if original is not None else error


def _api_exception_code(exc):
    """Map a DRF exception onto our codes, falling back on its status."""
    if isinstance(exc, (NotAuthenticated, DRFAuthenticationFailed)):
        return UNAUTHENTICATED
    if isinstance(exc, DRFPermissionDenied):
        return FORBIDDEN
    if isinstance(exc, Throttled):
        return RATE_LIMITED
    return BAD_REQUEST if exc.status_code < 500 else INTERNAL_ERROR


def classify(error):
    """Return ``(code, client_safe)`` for the exception behind ``error``.

    One pass decides both, so an error can never be given a meaningful code
    while having its message withheld, or vice versa.
    """
    root = _root_error(error)

    declared = (getattr(root, "extensions", None) or {}).get("code")
    if declared:
        # Choosing a coded error class is an opt-in that the message is meant
        # for the client, so default to disclosing it. An error that carries a
        # code but wraps something internal says so with `client_safe = False`
        # (see core.service_errors.ServiceErrorException).
        return declared, bool(getattr(root, "client_safe", True))

    if isinstance(root, JSONWebTokenError):
        return UNAUTHENTICATED, True
    if isinstance(root, DjangoPermissionDenied):
        return FORBIDDEN, True
    if isinstance(root, PermissionError):
        # openIMIS resolvers signal authZ failures with the builtin:
        # `raise PermissionError("Unauthorized")`, in ~59 places across modules.
        # PermissionError is really an OSError, so tell the two apart by errno:
        # a real filesystem EACCES sets it (and its message carries a path we
        # must not echo), a hand-raised one leaves it None.
        return (FORBIDDEN, True) if root.errno is None else (INTERNAL_ERROR, False)
    if isinstance(root, APIException):
        # DRF exceptions reach GraphQL too (login raises AuthenticationFailed).
        return _api_exception_code(root), root.status_code < 500
    if isinstance(root, DjangoValidationError):
        return BAD_REQUEST, True
    if isinstance(root, GraphQLError):
        # A deliberately raised GraphQLError, or a query the schema rejected.
        return BAD_REQUEST, True

    return INTERNAL_ERROR, False


def error_code_for(error):
    """Best-effort stable code for anything the GraphQL executor hands back."""
    return classify(error)[0]


def is_client_safe(error):
    """Whether this error's message was written for the client to read."""
    return classify(error)[1]


def safe_error_message(exc, debug=None):
    """The message to hand a client for ``exc``, hiding internals in production."""
    if debug is None:
        debug = settings.DEBUG
    if debug or is_client_safe(exc):
        return str(exc)
    return str(GENERIC_INTERNAL_MESSAGE)


def format_error(error, debug=None):
    """Render one executor error, guaranteeing ``extensions.code``.

    Unexpected exceptions keep their location/path but lose their message
    outside DEBUG -- a bare ``KeyError`` used to reach clients as the raw key
    name, which is both useless to them and a small information leak.
    """
    if debug is None:
        debug = settings.DEBUG

    if isinstance(error, GraphQLError):
        formatted = format_graphql_core_error(error)
    else:
        formatted = {"message": str(error)}

    code, client_safe = classify(error)
    extensions = dict(formatted.get("extensions") or {})
    extensions["code"] = code
    formatted["extensions"] = extensions

    if not debug and not client_safe:
        formatted["message"] = str(GENERIC_INTERNAL_MESSAGE)

    return formatted
