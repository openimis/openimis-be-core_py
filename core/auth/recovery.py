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
from core.auth import devices, revocation
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
