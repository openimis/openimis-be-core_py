"""Enrolling an authenticator, for a user who may not be able to log in.

The policy can bind a user who has no device, and such a user is refused by
every login until they have one - so enrolment cannot sit behind a session.
It authenticates with the password instead, the way the login itself does
before it asks for a code. Under the default policy that grants nothing: a
user with no confirmed device is one whose password was already enough.
Under a binding policy it is the bootstrap every second-factor system
accepts, and the reason the refusal below exists - a user who already has a
device cannot be given another by whoever holds their password.

Authenticator apps only. A channel that sends the code is a device class plus
a gateway, and the README's login section already says what that takes.
"""

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

#: A confirmed device exists; a second one is not added on the password alone.
SECOND_FACTOR_ALREADY_ENROLLED = "SECOND_FACTOR_ALREADY_ENROLLED"

#: The only method that can be enrolled today. A channel that sends the code -
#: SMS, WhatsApp - is a second value here, a device class, and a gateway; what
#: it is not is a second confirmation step, since confirming is the same
#: exchange whatever produced the code.
TOTP = "TOTP"


def begin(request, username, password):
    """Verify the password and hand back a fresh, unconfirmed authenticator.

    Password failures raise what user_authentication raises, unchanged, and
    Django's authenticate() has already reported them to the lockout by then.
    """
    user = user_authentication(request, username, password)
    if devices.has_second_factor(user):
        raise SecondFactorError(SECOND_FACTOR_ALREADY_ENROLLED)
    return devices.enrol_totp(user)


def secret(device):
    """The shared secret as an authenticator app takes it by hand: base32,
    the same encoding config_url carries."""
    return b32encode(device.bin_key).decode()


def complete(request, username, password, otp):
    """Confirm the pending authenticator with a code from it, and return the
    user's first recovery codes.

    Not a login, so a wrong code here is not reported to the account lockout:
    the caller was handed the secret the code derives from a moment ago, so a
    wrong one is mistyped or stale, not a guess - and the lockout budget is
    per address. django-otp's per-device back-off is the rate limit that fits.
    """
    user = user_authentication(request, username, password)

    # One transaction over the lock, the confirmation and the codes. The
    # pending row is locked first, so two confirmations racing on it
    # serialise and the second finds a confirmed device rather than replacing
    # the set the first already returned; and a failure issuing the codes
    # rolls the confirmation back, so a confirmed device never exists without
    # them - the user simply retries with the next code.
    with transaction.atomic():
        device = devices.pending_totp(user, for_update=True)
        if devices.has_second_factor(user):
            raise SecondFactorError(SECOND_FACTOR_ALREADY_ENROLLED)
        if device is None:
            raise SecondFactorError(SECOND_FACTOR_ENROLMENT_REQUIRED)
        if not otp:
            # Ahead of the device: an empty submission would still charge
            # its back-off.
            raise SecondFactorError(SECOND_FACTOR_REQUIRED)
        allowed, reason = device.verify_is_allowed()
        if not allowed:
            # confirm_totp would answer False here too, indistinguishable
            # from a wrong code; asking first is what lets the client be
            # told to wait rather than retype.
            lifted = (reason or {}).get("locked_until")
            raise SecondFactorError(
                SECOND_FACTOR_THROTTLED,
                lockedUntil=lifted.isoformat() if lifted else None,
            )
        if devices.confirm_totp(device, otp):
            return devices.issue_recovery_codes(user)
        # Falling out of the block rather than raising inside it. verify_token
        # has just charged this device a throttle failure, and an exception
        # here would roll that back along with everything else - leaving the
        # guessing unmetered, since a wrong code is deliberately not reported
        # to the account lockout either.
    raise SecondFactorError(INVALID_SECOND_FACTOR)
