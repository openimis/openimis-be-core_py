"""Getting back into an account whose second factor is lost.

Two ways, deliberately unequal. A user who still holds a device re-issues
their own recovery codes in exchange for a current code, so a stolen session
alone cannot mint a bypass for the factor it stole its way past. A user who
holds nothing needs an administrator, and that path is gated by a right, ends
every session, and leaves a record - which is why it lives behind a mutation
rather than behind the device pages the Django admin would otherwise offer.

Nothing here verifies a login or decides who must present a second factor.
Both of those stay in core.auth.login, which this module does not change.
"""

from gettext import gettext as _

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed

from core.apps import CoreConfig
from core.auth import devices, revocation, second_factor
from core.auth.login import (
    INVALID_SECOND_FACTOR,
    SECOND_FACTOR_ENROLMENT_REQUIRED,
    SECOND_FACTOR_REQUIRED,
    SECOND_FACTOR_THROTTLED,
    SecondFactorError,
)
from core.models.user import User


def reset_second_factor(logged_user, user_uuid):
    """Remove every second-factor device a user has and end their sessions.

    Refused for a user with no interactive row: the revocation point lives in
    InteractiveUser.json_ext, so a technical account's sessions cannot be
    ended, and removing their devices alone would leave exactly the half-state
    this exists to prevent - a lost device disarmed while the session it
    opened stays alive.
    """
    if not logged_user.has_perms(CoreConfig.gql_mutation_reset_second_factor_perms):
        raise AuthenticationFailed("unauthorized")
    user = User.objects.get(id=user_uuid)
    if not user.i_user:
        raise ValidationError(_("core.user.not_interactive"))

    with transaction.atomic():
        devices.remove_all(user)
        revocation.bump(user.i_user)
        # silent: a bump inside the same second as an earlier one writes the
        # identical value, and OpenIMISModel.save() rejects a no-op update.
        user.i_user.save(silent=True)
        # The not-before already covers single-token refresh, which re-decodes
        # what it is handed; this also covers a deployment running long-lived
        # refresh tokens.
        user.clear_refresh_tokens()
    return user


def reissue_recovery_codes(user, otp, otp_device=None):
    """Replace the user's recovery set and return the new codes, once.

    The price is a current code from one of their own devices - a recovery
    code included, since whoever holds a valid one can already log in and
    refilling the set gives them nothing further. Raises with the codes the
    login uses, so a client can answer both the same way.

    Not a login, so a wrong code here is not reported to the account lockout:
    the caller already holds a session, and the lockout budget is scoped to
    the address rather than the account. django-otp's per-device back-off,
    which verify applies, is the rate limit that belongs here.
    """
    if not devices.has_second_factor(user):
        raise SecondFactorError(SECOND_FACTOR_ENROLMENT_REQUIRED)
    if not otp:
        # Ahead of verify so an empty submission does not spend back-off
        # budget on every device the user owns.
        raise SecondFactorError(SECOND_FACTOR_REQUIRED)

    result = second_factor.verify(user, otp, device_id=otp_device)
    if result.outcome == second_factor.THROTTLED:
        lifted = result.locked_until.isoformat() if result.locked_until else None
        raise SecondFactorError(SECOND_FACTOR_THROTTLED, lockedUntil=lifted)
    if not result.ok:
        raise SecondFactorError(INVALID_SECOND_FACTOR)
    return devices.issue_recovery_codes(user)
