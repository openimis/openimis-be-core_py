"""Enrolment of second-factor devices.

django-otp ships the models; this module owns their lifecycle. Nothing here
verifies a login code - that is core.auth.second_factor, which must stay free of
any particular device class.
"""

from django.db import transaction
from django_otp import device_classes, devices_for_user, user_has_device
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

#: One static device per user holds the whole recovery set; the name is how it is
#: found again, since a user never has more than one.
RECOVERY_DEVICE_NAME = "Recovery codes"
RECOVERY_CODE_COUNT = 10


def enrol_totp(user, name="Authenticator app"):
    """A new, *unconfirmed* TOTP device and its secret.

    Unconfirmed is the point: `devices_for_user` is confirmed-only, so a scan
    that is never followed by a matching code can satisfy nothing. Any earlier
    unconfirmed device is dropped first - it is an abandoned attempt, and
    leaving it behind would let a stale QR code be completed later.
    """
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(user=user, name=name, confirmed=False)


def confirm_totp(device, token):
    """Activate `device` if `token` came from it. Returns whether it did.

    Only the name is about authenticator apps: verifying a token and marking
    the device confirmed is the same for a device that was sent its code, so a
    channel added later confirms through this rather than through a copy.
    """
    if not device.verify_token(token):
        return False
    device.confirmed = True
    device.save(update_fields=["confirmed"])
    return True


@transaction.atomic
def issue_recovery_codes(user, count=RECOVERY_CODE_COUNT):
    """Replace the user's recovery set and return the new codes in clear.

    Returned once and never again: they are stored to be matched, and the only
    way back from a lost set is to re-issue, which is why this replaces rather
    than appends.
    """
    device, _ = StaticDevice.objects.get_or_create(
        user=user, name=RECOVERY_DEVICE_NAME
    )
    device.token_set.all().delete()
    codes = [StaticToken.random_token() for _ in range(count)]
    StaticToken.objects.bulk_create(
        StaticToken(device=device, token=code) for code in codes
    )
    return codes


def confirmed_devices(user):
    """Every confirmed device, of every installed device class."""
    return list(devices_for_user(user, confirmed=True))


def pending_totp(user, for_update=False):
    """The authenticator the user has most recently scanned but not confirmed.

    Normally there is only one, since enrol_totp drops any earlier unconfirmed
    device before creating the next - but it does so in two statements, so two
    concurrent enrolments can leave two behind. Newest first rather than
    unordered, because the row the caller wants is the one whose QR code the
    user is looking at; an arbitrary pick would leave their fresh code
    confirming nothing.

    `for_update` locks the row for the caller's transaction, so two
    confirmations racing on it serialise instead of both completing.

    Authenticators only, and deliberately not widened to every device class
    ahead of there being a second one: picking between classes needs an
    ordering the Device base class does not give, so it would be a guess with
    nothing to test it against. A channel that sends the code adds its own
    lookup here and a line in core.auth.enrolment.complete to consult it.
    """
    queryset = TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-id")
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.first()


def has_second_factor(user):
    return user_has_device(user, confirmed=True)


def remove_all(user):
    """Every device the user has, confirmed or not, of every installed class.

    The administrator-reset primitive. It ends nothing by itself: a caller
    that means "start this user over" pairs it with
    core.auth.revocation.bump(user.i_user), so any session a lost device may
    have opened ends at the same moment the device stops counting.
    """
    for model in device_classes():
        model.objects.filter(user=user).delete()
