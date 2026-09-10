"""Per-user not-before, the explicit replacement for rotating the password salt.

`InteractiveUser.set_password` mints a fresh `private_key`, which is at once the
password salt and, on the legacy path, the key a token is signed with. Changing
a password therefore stops every outstanding token verifying - revocation as a
side effect of the signature, not as a decision anyone recorded. Signing with a
single deployment-wide key removes that side effect, so the revocation point has
to be stored and checked explicitly instead. Nothing else ends a session.
"""

from calendar import timegm
from datetime import datetime

import jwt
from django.apps import apps

#: Key inside `InteractiveUser.json_ext`. `tblUsers.Json_ext` (jsonb) already
#: exists, so storing the revocation point needs no migration.
NOT_BEFORE_KEY = "tokens_not_before"


def _now():
    # Epoch seconds, UTC: the units `iat`, `nbf` and `origIat` carry, so the
    # comparison in assert_not_revoked needs no conversion.
    return timegm(datetime.utcnow().utctimetuple())


def user_not_before(username):
    """The user's revocation point as epoch seconds, or None if they have none.

    Resolved through `core_User.username` and the `i_user` foreign key, both
    indexed, and together the same path authentication uses to turn a token's
    `username` claim into a user. `tblUsers.LoginName` carries no index, so
    reading the row by login name would add a sequential scan to every
    authenticated request.

    A user with no `core_User` row reads as None. Not a gap: without that row
    the token cannot authenticate at all, so there is no session to end.

    `values_list` resolves through `Manager.get_queryset()` and returns a plain
    QuerySet, which is what takes the following `filter` past
    `CachedManager.filter`. Deliberate, and the reason this is a query rather
    than a cache read: the object cache is per-process by default
    (`LocMemCache`) and caches the interactive user together with the user row,
    so a cached read would leave a revoked token working on every worker except
    the one that revoked it.
    """
    user = apps.get_model("core", "User")
    json_ext = (
        user.objects.values_list("i_user__json_ext", flat=True)
        .filter(username=username)
        .first()
    )
    return (json_ext or {}).get(NOT_BEFORE_KEY)


def bump(i_user):
    """Move an interactive user's revocation point to now, in memory.

    Deliberately does not save. Every caller is already saving the same instance
    for another reason, and doing it here would double the writes.

    Assigns a copy instead of mutating `json_ext` in place, so nothing holding a
    reference to the stored dict - a dirty-field snapshot, a cached copy -
    observes the change before the save does.

    The value never decreases. Two workers whose clocks disagree would otherwise
    let the lagging one lower the bar and bring already-rejected tokens back.
    """
    json_ext = dict(i_user.json_ext) if isinstance(i_user.json_ext, dict) else {}
    current = json_ext.get(NOT_BEFORE_KEY)
    moment = _now()
    if isinstance(current, (int, float)) and current > moment:
        moment = current
    json_ext[NOT_BEFORE_KEY] = moment
    i_user.json_ext = json_ext
    return moment


def assert_not_revoked(claims):
    """Reject a token issued before its user's revocation point.

    Raises `jwt.InvalidTokenError` and nothing else, which is the whole
    contract: `graphql_jwt.utils.get_payload` turns that one exception into an
    authentication failure and lets every other kind through as a 500. Hence the
    type checks rather than a bare comparison - `origIat` is a graphql_jwt claim
    that PyJWT does not validate, so a non-numeric one reaches here intact and
    `<` alone would raise TypeError.
    """
    not_before = user_not_before(claims.username)
    if not isinstance(not_before, (int, float)):
        # No revocation point, or something unusable where one should be. Both
        # read as absent: enforcing a value that cannot be compared could only
        # lock the user out, and this module is the only thing that writes it.
        return
    if not isinstance(claims.issued_at, (int, float)):
        # Fail closed. Nothing in the token places it after the revocation
        # point, so it cannot be shown to have outlived the change.
        raise jwt.InvalidTokenError("token has no comparable issue time")
    if claims.issued_at < not_before:
        raise jwt.InvalidTokenError("token issued before revocation point")
