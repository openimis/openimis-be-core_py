"""Enrolling a second factor, for a user who may not be able to log in.

A deployment policy can bind a user who has no device, and every login refuses
them until they have one - so for that user enrolment cannot sit behind a
session, and the password is enough. A user the policy leaves free is
different: the password alone already logs them in, and letting it also bind
an authenticator would let whoever stole it lock the owner out for good - a
password reset removes no device. So for them enrolment needs their own login
as well as the password. One who already has a device is refused either way,
so a password is never enough to add a second.
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
    mfa_required,
)
from core.services.userServices import user_authentication

logger = logging.getLogger(__name__)

#: A confirmed device exists; a second one is not added on the password alone.
SECOND_FACTOR_ALREADY_ENROLLED = "SECOND_FACTOR_ALREADY_ENROLLED"
#: The policy leaves this user free to log in on the password, so enrolling
#: needs that login too.
SECOND_FACTOR_LOGIN_REQUIRED = "SECOND_FACTOR_LOGIN_REQUIRED"

#: The only method enrollable today. Another is a further value here and its
#: own material to hand back; confirming stays the same exchange whatever
#: produced the code.
TOTP = "TOTP"


def _enrolling_user(request, username, password):
    """The user whose password this is, if they may enrol from this request.

    The caller is read before the password is checked: user_authentication
    clears the JWT cookies from the request.
    """
    caller = getattr(request, "user", None)
    user = user_authentication(request, username, password)
    signed_in_as_them = bool(
        caller is not None and caller.is_authenticated and caller.id == user.id
    )
    if not mfa_required(user) and not signed_in_as_them:
        raise SecondFactorError(SECOND_FACTOR_LOGIN_REQUIRED)
    return user


def begin(request, username, password):
    """Verify the password and hand back a fresh, unconfirmed authenticator.

    A wrong password raises out of user_authentication, which has already
    reported it to the account lockout; nothing here repeats that.
    """
    user = _enrolling_user(request, username, password)
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
    user = _enrolling_user(request, username, password)

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
