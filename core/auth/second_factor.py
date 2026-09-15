"""Verification of a second factor, across every device class a user has.

Deliberately not `django_otp.match_token`, which its own docstring deprecates:
"not guaranteed to interact well with more recent features (such as
throttling)". Both shipped device types mix in ThrottlingMixin, so a loop that
tries each in turn charges a failure to every device that is not the one the
code came from - a user falling back to a recovery code would back their
authenticator off exponentially. This owns the loop instead, and undoes those
collateral failures once some device accepts the code.

Nothing here names a device class. `devices_for_user` walks every installed
Device subclass, so an SMS or WhatsApp channel is a new subclass plus a gateway
and this module does not change.
"""

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django_otp import devices_for_user
from django_otp.models import Device

#: A device accepted the code; `Verification.device` is which one.
VERIFIED = "verified"
#: Devices were tried and none accepted it.
INVALID = "invalid"
#: The user has no confirmed device - or named one that is not theirs.
NO_DEVICES = "no_devices"
#: Every candidate device is backing off; nothing was even tried.
THROTTLED = "throttled"


@dataclass(frozen=True)
class Verification:
    """One attempt's result: an `outcome` constant from above, not a bool,
    because the caller answers differently to each."""

    outcome: str
    device: Device = None
    locked_until: datetime = None

    @property
    def ok(self):
        return self.outcome == VERIFIED


#: ThrottlingMixin's fields, not Device's - a device class can opt out of
#: throttling, and then it has neither these nor `throttle_reset`.
_THROTTLE_FIELDS = ("throttling_failure_count", "throttling_failure_timestamp")


def _throttle_state(device):
    """This device's throttling counters, or None if its class does not throttle."""
    if not all(hasattr(device, field) for field in _THROTTLE_FIELDS):
        return None
    return tuple(getattr(device, field) for field in _THROTTLE_FIELDS)


def _restore_throttle(device, state):
    """Undo the failure this attempt charged to a device the code was not for.

    Restores the counters rather than calling `throttle_reset`, which zeroes
    them. Zeroing would mean every legitimate fallback login wiped a back-off an
    attacker had built up on the other device, handing them a fresh budget.
    """
    if state is None or _throttle_state(device) == state:
        return
    for field, value in zip(_THROTTLE_FIELDS, state):
        setattr(device, field, value)
    device.save(update_fields=list(_THROTTLE_FIELDS))


def _earliest_lift(blocked):
    stamps = [info.get("locked_until") for info in blocked if info]
    stamps = [stamp for stamp in stamps if stamp is not None]
    return min(stamps) if stamps else None


def _candidates(user, device_id):
    if device_id is None:
        return list(devices_for_user(user, confirmed=True, for_verify=True))
    try:
        device = Device.from_persistent_id(device_id, for_verify=True)
    except (AttributeError, TypeError):
        # from_persistent_id suppresses ValueError and LookupError but not
        # these: an id naming a real model that is not a Device ("core.user/1")
        # leaves it calling .first() on None, and a non-string id has no
        # .rsplit. Both arrive from a client, so a bad id is "no such device".
        return []
    # Ownership and confirmation are checked here rather than trusted from the
    # id: persistent_id is a model label and a primary key, both guessable.
    if device is None or device.user_id != user.pk or not device.confirmed:
        return []
    return [device]


def verify(user, token, device_id=None):
    """Verify `token` for `user`, against one named device or against all of them.

    `device_id` is a `Device.persistent_id`. Passing one is the path a channel
    that must *send* a code first will use, and it avoids the collateral
    throttling below entirely; passing none tries everything the user has.
    """
    if isinstance(token, str):
        # A static token is lowercase base32 compared exactly, so a recovery
        # code retyped in upper case - which a phone keyboard does by itself -
        # would miss *and* charge a throttle failure to every device the user
        # has. A TOTP token is digits, so folding case here costs nothing.
        token = token.strip().lower()

    # One transaction: devices_for_user(for_verify=True) selects for update, so
    # two concurrent attempts cannot both spend the same recovery code.
    with transaction.atomic():
        candidates = _candidates(user, device_id)
        if not candidates:
            return Verification(NO_DEVICES)

        attempted, blocked = [], []
        for device in candidates:
            allowed, reason = device.verify_is_allowed()
            if not allowed:
                # A throttled device's own verify_token would return False
                # without incrementing; skipping it explicitly is the same
                # outcome, and it is what lets us report locked_until.
                blocked.append(reason)
                continue
            attempted.append((device, _throttle_state(device)))
            if device.verify_token(token):
                # Every device tried before this one just took a failure for a
                # code that was never meant for it. Undo those, and only those:
                # the device that matched has reset its own counter already.
                for collateral, state in attempted[:-1]:
                    _restore_throttle(collateral, state)
                return Verification(VERIFIED, device=device)

        if not attempted:
            return Verification(THROTTLED, locked_until=_earliest_lift(blocked))
        return Verification(INVALID)
