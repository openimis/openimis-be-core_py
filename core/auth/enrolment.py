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

from core.auth import devices
from core.auth.login import SecondFactorError
from core.services.userServices import user_authentication

#: A confirmed device exists; a second one is not added on the password alone.
SECOND_FACTOR_ALREADY_ENROLLED = "SECOND_FACTOR_ALREADY_ENROLLED"


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
