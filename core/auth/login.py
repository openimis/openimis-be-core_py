"""The login exchange: a password, then - for a user who has one - a second factor.

One function, two callers: the tokenAuth mutation (core.schema) and
api_fhir_r4's LoginView, which take the same credentials over different
transports and mint the same JWT. Both call authenticate_login and map
SecondFactorError to their own error shape; neither decides anything about the
second factor itself, so a new channel or a policy change lands here once.

Nothing here mints a token or opens a session. The caller does both after this
returns - which is what keeps the second factor ahead of the token and the
session a login issues. It does not reach the credentials no login flow hands
out: HTTP Basic, accepted per request on every REST and FHIR view, and the
Django admin's own form, both of which still take a password on its own.
"""

from django.contrib.auth.signals import user_login_failed

from core.auth import devices, second_factor
from core.services.userServices import user_authentication

#: Password accepted; the user has a confirmed device and sent no code.
SECOND_FACTOR_REQUIRED = "SECOND_FACTOR_REQUIRED"
#: A code was sent and no device of the user's accepted it.
INVALID_SECOND_FACTOR = "INVALID_SECOND_FACTOR"
#: Every device the code could be for is backing off; nothing was tried.
SECOND_FACTOR_THROTTLED = "SECOND_FACTOR_THROTTLED"


class SecondFactorError(Exception):
    """The password was right and the second factor was missing or wrong.

    str() is the code, so a GraphQL caller that lets it propagate produces
    errors[0].message == code - the shape INCORRECT_CREDENTIALS already has.
    `extensions` is copied onto the GraphQL error by graphql-core
    (GraphQLLocatedError reads it off original_error), so detail such as
    lockedUntil reaches the client without the mutation touching it.
    """

    def __init__(self, code, **extensions):
        super().__init__(code)
        self.code = code
        # Always carries the code too: extensions.code is where GraphQL
        # clients conventionally look, message is where this schema puts it.
        self.extensions = {"code": code, **extensions}


def mfa_required(user):
    """Whether this login must present a second factor.

    Enrolment is the policy for now: a user with a confirmed device must use
    it. The role- and deployment-aware predicate replaces this body; it stays
    the one place the question is asked.
    """
    return devices.has_second_factor(user)


def authenticate_login(request, username, password, otp=None, otp_device=None):
    """Verify the whole login and return the user, or raise.

    Password failures raise what user_authentication raises today, unchanged,
    and before any second factor is looked at. A user for whom mfa_required
    holds must also pass `otp` - a code from any confirmed device, or from the
    one `otp_device` names (a Device.persistent_id). Both arrive straight from
    the client.
    """
    user = user_authentication(request, username, password)
    if not mfa_required(user):
        return user
    if not otp:
        raise SecondFactorError(SECOND_FACTOR_REQUIRED)

    result = second_factor.verify(user, otp, device_id=otp_device)
    if result.ok:
        return user

    if result.outcome == second_factor.THROTTLED:
        # Deliberately ahead of the signal below: no device was tried, so
        # nothing was guessed wrong. axes' budget is scoped to the IP by
        # default, and charging the retries a user makes during django-otp's
        # back-off would lock out everyone behind it.
        lifted = result.locked_until.isoformat() if result.locked_until else None
        raise SecondFactorError(SECOND_FACTOR_THROTTLED, lockedUntil=lifted)

    # Counted like a wrong password: axes listens for this signal, and the
    # lockout budget is per login, not per factor.
    user_login_failed.send(
        sender=__name__, credentials={"username": username}, request=request
    )
    # INVALID and NO_DEVICES both land here on purpose: NO_DEVICES with an
    # otp_device means the id named a device that is not this user's, and a
    # distinct answer would confirm the id exists.
    raise SecondFactorError(INVALID_SECOND_FACTOR)
