"""Enrolling a second factor, for a user who may not be able to log in.

A deployment policy can bind a user who has no device, and every login refuses
them until they have one - so enrolment cannot sit behind a session. It takes
the password instead. That makes an account without a device exactly as strong
as its password: whoever holds it can bind an authenticator the owner does not
have, and only an administrator's reset undoes that. One who does have a device
is refused, so a password is never enough to add a second.
"""

import logging
from base64 import b32encode

from django.db import transaction

from core.auth import devices
from core.auth.login import (
    INVALID_SECOND_FACTOR,
    SECOND_FACTOR_ENROLMENT_REQUIRED,
    SECOND_FACTOR_REQUIRED,
    SECOND_FACTOR_THROTTLED,
    SecondFactorError,
)
from core.services.userServices import user_authentication

logger = logging.getLogger(__name__)

#: A confirmed device exists; a second one is not added on the password alone.
SECOND_FACTOR_ALREADY_ENROLLED = "SECOND_FACTOR_ALREADY_ENROLLED"

#: The only method enrollable today. Another is a further value here and its
#: own material to hand back; confirming stays the same exchange whatever
#: produced the code.
TOTP = "TOTP"


def _password_owner(request, username, password):
    """The user whose password this is, checked on the password alone.

    authenticate() would otherwise answer from a token on the request -
    graphql_jwt's backend reads it before the password backend runs - and a
    token would stand in for the password. The flag is the one tokenAuth sets
    for the same reason.
    """
    request._jwt_token_auth = True
    return user_authentication(request, username, password)


def begin(request, username, password):
    """Verify the password and hand back a fresh, unconfirmed authenticator.

    A wrong password raises out of user_authentication, which has already
    reported it to the account lockout; nothing here repeats that.
    """
    user = _password_owner(request, username, password)
    if devices.has_second_factor(user):
        raise SecondFactorError(SECOND_FACTOR_ALREADY_ENROLLED)
    return devices.enrol_totp(user)


def secret(device):
    """The shared secret in base32 - the encoding config_url carries, and what
    an authenticator app accepts when it is typed in by hand."""
    return b32encode(device.bin_key).decode()


def complete(request, username, password, otp):
    """Confirm the pending authenticator with a code from it, and return the
    user's first recovery codes.

    A wrong code is not reported to the account lockout: the caller was handed
    the secret it derives from moments ago, so a wrong one is mistyped rather
    than guessed, and the lockout budget is per address. The device's own
    back-off is the rate limit instead.
    """
    user = _password_owner(request, username, password)

    # One transaction over the lock, the confirmation and the codes: locking
    # the pending row first serialises two racing confirmations, and rolling
    # back together means a confirmed device never exists without the recovery
    # set, which is only ever returned once.
    with transaction.atomic():
        device = devices.pending_totp(user, for_update=True)
        if devices.has_second_factor(user):
            raise SecondFactorError(SECOND_FACTOR_ALREADY_ENROLLED)
        if device is None:
            raise SecondFactorError(SECOND_FACTOR_ENROLMENT_REQUIRED)
        if not otp:
            # Ahead of the device, so an empty submission charges no back-off.
            raise SecondFactorError(SECOND_FACTOR_REQUIRED)
        allowed, reason = device.verify_is_allowed()
        if not allowed:
            # Asked explicitly because confirm_totp answers False for a
            # backing-off device too, which a client reads as a wrong code.
            lifted = (reason or {}).get("locked_until")
            raise SecondFactorError(
                SECOND_FACTOR_THROTTLED,
                lockedUntil=lifted.isoformat() if lifted else None,
            )
        if devices.confirm_totp(device, otp):
            # The only trace that a factor was bound to this account: these
            # mutations stay out of the mutation log, which would record the
            # password alongside whatever it recorded of the event.
            logger.info("Second factor enrolled for %s", user.username)
            return devices.issue_recovery_codes(user)
        # Not raised inside the block: verify_token has just charged this
        # device a throttle failure, and rolling that back would leave the
        # guessing unmetered.
    raise SecondFactorError(INVALID_SECOND_FACTOR)
