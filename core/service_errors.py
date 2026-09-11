"""Typed, validated wrapper around the openIMIS service error payload.

openIMIS services report failure **in band**: they return a result dict instead
of raising. That is deliberate and stays. A GraphQL response must be HTTP 200
even when the operation failed -- the spec reserves transport status for
transport problems -- and an async mutation reports through MutationLog long
after the HTTP response is gone, so there is no exception left to raise.

What this module adds is a *type* for that payload. Today the dict is built
ad hoc in ~108 places and every field is a free-form string, so nothing can be
validated and no consumer can branch without matching message text. A
``ServiceError``:

* validates what it is given (closed ``code`` vocabulary, non-empty message),
  so a malformed payload fails where it is built rather than where it is read;
* renders to the **exact** legacy keys, plus ``code`` -- purely additive, so
  existing consumers are untouched and new ones can branch on the code;
* parses a legacy payload back into a typed object (``from_dict``), which is
  what lets an API edge convert a service result into a GraphQL error, a DRF
  response, or a FHIR OperationOutcome.

That last point is the forward path. Nothing here raises or changes a status
code; this is the seam a cleaner solution plugs into, not the cleaner solution
itself. Two things are deliberately left alone:

* ``detail`` is still the verbatim exception text. Modules legitimately put
  domain messages there (``"ContractUpdateError: You cannot update already set
  PolicyHolder in Contract!"``), so sanitising it wholesale would swallow real
  information. Narrowing it needs each module to say which of its errors are
  client-safe -- i.e. to raise typed errors -- and that is the follow-up.
* The payload keeps reporting success/failure in band. Only the ``code`` field
  is new.
"""

import logging
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from core.gql_errors import (
    CodedGraphQLError,
    ERROR_CODES,
    INTERNAL_ERROR,
    classify,
)

logger = logging.getLogger(__name__)

# Keys a legacy service payload is made of. Kept explicit so a change to the
# wire shape is a visible edit here rather than an emergent side effect.
SUCCESS_KEY = "success"
MESSAGE_KEY = "message"
DETAIL_KEY = "detail"
DATA_KEY = "data"
CODE_KEY = "code"
FIELD_ERRORS_KEY = "field_errors"

_EMPTY_FIELD_ERRORS = MappingProxyType({})


class ServicePayload(dict):
    """The legacy service payload, with the typed error attached alongside.

    Exactly the same keys and values as the hand-built dict it replaces, so
    ``assertDictEqual`` against a literal still passes, ``json.dumps`` produces
    the same JSON, and any consumer reading keys is unaffected. The typed error
    rides as an *attribute*, which is why adding it breaks nothing.

    ``error`` is in-process only: it does not survive ``json.dumps``, a
    ``dict(payload)`` copy, or a trip through MutationLog. Read it while the
    payload is still the object the service returned; otherwise fall back to
    ``ServiceError.from_dict``, which reads the keys.
    """

    __slots__ = ("error",)

    def __init__(self, items, error):
        super().__init__(items)
        self.error = error


def _normalise_field_errors(value):
    """Coerce per-field errors to an immutable ``{field: (message, ...)}``."""
    if not value:
        return _EMPTY_FIELD_ERRORS
    if not isinstance(value, Mapping):
        raise TypeError(f"field_errors must be a mapping, got {type(value).__name__}")
    normalised = {}
    for name, messages in value.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"field_errors keys must be non-empty strings: {name!r}")
        if isinstance(messages, str):
            messages = (messages,)
        normalised[name] = tuple(str(message) for message in messages)
    return MappingProxyType(normalised)


@dataclass(frozen=True)
class ServiceError:
    """One service failure, validated at construction.

    Frozen so a payload cannot be mutated after the checks below have run.
    """

    code: str
    message: str
    detail: str = ""
    data: Any = ""
    field_errors: Mapping[str, tuple] = field(default_factory=dict)

    # Whether the rendered payload carries a "data" key. output_exception has
    # always emitted one; the access-control payloads never have. Preserved
    # per-site so neither shape shifts.
    include_data: bool = True

    # The exception this was built from, when it is still available. Kept so a
    # caller that decides the failure should propagate can re-raise the real
    # thing -- original type, message and traceback -- instead of a
    # reconstruction. Deliberately excluded from equality (two payloads that say
    # the same thing are the same error) and from repr (a traceback in a log
    # line is noise). It never reaches as_dict(), so nothing serialises it and
    # from_dict() cannot recover it: treat it as in-process only, valid for the
    # life of the request that produced it. Holding it also holds its traceback
    # and therefore the frames' locals, so do not cache a ServiceError.
    exception: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self):
        if self.code not in ERROR_CODES:
            raise ValueError(
                f"unknown error code {self.code!r}; expected one of {ERROR_CODES}"
            )
        # gettext_lazy proxies are legitimate inputs, so coerce rather than
        # reject, but a None or a stray object must not become the string
        # "None" silently.
        if self.message is None:
            raise ValueError("message is required")
        message = str(self.message).strip()
        if not message:
            raise ValueError("message must not be empty")

        if self.exception is not None and not isinstance(self.exception, BaseException):
            raise TypeError(
                f"exception must be an exception, got {type(self.exception).__name__}"
            )

        object.__setattr__(self, "message", message)
        object.__setattr__(self, "detail", "" if self.detail is None else str(self.detail))
        object.__setattr__(
            self, "field_errors", _normalise_field_errors(self.field_errors)
        )

    # -- construction --------------------------------------------------------

    @classmethod
    def from_exception(cls, exception, message, **extra):
        """Build from a caught exception, taking the code from its type.

        Uses the same classification as the GraphQL formatter, so one exception
        is reported with one code no matter which API surfaces it.
        """
        code, _client_safe = classify(exception)
        if code not in ERROR_CODES:
            # classify() can echo a code declared on the exception itself; keep
            # the vocabulary closed rather than trusting arbitrary input.
            logger.warning(
                "Exception %s declared unknown error code %r; using %s",
                type(exception).__name__,
                code,
                INTERNAL_ERROR,
            )
            code = INTERNAL_ERROR
        extra.setdefault("exception", exception)
        return cls(code=code, message=message, detail=str(exception), **extra)

    @classmethod
    def from_dict(cls, payload):
        """Recover a ``ServiceError`` from a legacy payload.

        Returns ``None`` when the payload does not describe a failure, so an
        API edge can do ``error = ServiceError.from_dict(result)`` and act only
        when there is something to report. Unparseable payloads come back as an
        ``INTERNAL_ERROR`` rather than raising: this runs on a path that is
        already handling a failure.
        """
        if not isinstance(payload, Mapping):
            return None
        if payload.get(SUCCESS_KEY, True):
            return None

        # A payload straight from a service still has the typed error, with its
        # code and originating exception intact; prefer it over re-deriving.
        attached = getattr(payload, "error", None)
        if isinstance(attached, cls):
            return attached

        message = payload.get(MESSAGE_KEY) or "Service call failed"
        code = payload.get(CODE_KEY)
        if code not in ERROR_CODES:
            code = INTERNAL_ERROR
        try:
            return cls(
                code=code,
                message=message,
                detail=payload.get(DETAIL_KEY) or "",
                data=payload.get(DATA_KEY, ""),
                include_data=DATA_KEY in payload,
                field_errors=payload.get(FIELD_ERRORS_KEY) or {},
            )
        except (TypeError, ValueError):
            logger.warning("Could not parse service error payload: %r", payload)
            return cls(code=INTERNAL_ERROR, message="Service call failed")

    @staticmethod
    def is_error_payload(payload):
        """Whether ``payload`` is a service result reporting failure."""
        return isinstance(payload, Mapping) and not payload.get(SUCCESS_KEY, True)

    # -- rendering -----------------------------------------------------------

    def as_dict(self, with_code=False):
        """The legacy payload, as a :class:`ServicePayload`.

        The keys are unchanged from the hand-built dict: ``success``,
        ``message``, ``detail`` and -- unless ``include_data`` is false --
        ``data``. The code is reachable through the payload's ``error``
        attribute rather than as a key, so that adding it cannot break a
        consumer or a test asserting the exact dict.

        Pass ``with_code=True`` to also emit ``code`` (and ``field_errors``) as
        keys, for a surface that has no other channel -- an HTTP body, say.
        Making that the default is the follow-up, once every module's payload
        assertions have been updated to expect it.
        """
        payload = {
            SUCCESS_KEY: False,
            MESSAGE_KEY: self.message,
            DETAIL_KEY: self.detail,
        }
        if self.include_data:
            payload[DATA_KEY] = self.data
        if with_code:
            payload[CODE_KEY] = self.code
            if self.field_errors:
                payload[FIELD_ERRORS_KEY] = {
                    name: list(messages)
                    for name, messages in self.field_errors.items()
                }
        return ServicePayload(payload, self)

    def reraise(self):
        """Propagate this failure as an exception.

        Re-raises the original exception when it was retained, so the type and
        traceback survive; otherwise raises ``ServiceErrorException`` carrying
        this payload. Use it where a service result has been inspected and the
        caller has decided the failure should not be swallowed -- notably an API
        edge that wants the error out of band rather than in the payload.
        """
        if self.exception is not None:
            raise self.exception
        raise ServiceErrorException(self)

    def to_graphql_error(self):
        """This failure as a GraphQL error, for callers that report out of band.

        Unused by the in-band mutation path; it exists so a resolver that
        *should* fail the field (a denied query, say) has one line to do it
        with, instead of returning a dict graphene cannot coerce.
        """
        error = CodedGraphQLError(self.message)
        error.extensions = {**(error.extensions or {}), CODE_KEY: self.code}
        if self.field_errors:
            error.extensions[FIELD_ERRORS_KEY] = {
                name: list(messages) for name, messages in self.field_errors.items()
            }
        return error


class ServiceErrorException(Exception):
    """A ``ServiceError`` raised as an exception.

    Used by :meth:`ServiceError.reraise` when the original exception is no
    longer available -- for instance after a payload has crossed a process
    boundary and been rebuilt with ``from_dict``.

    It declares ``extensions`` so the GraphQL formatter picks up the code with
    no special-casing, and ``client_safe`` so an INTERNAL_ERROR payload does not
    have its message disclosed just because the code was declared explicitly.
    """

    def __init__(self, error):
        super().__init__(error.message)
        self.error = error
        self.extensions = {CODE_KEY: error.code}
        self.client_safe = error.code != INTERNAL_ERROR
