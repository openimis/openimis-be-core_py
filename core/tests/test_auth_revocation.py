import json
from calendar import timegm
from datetime import datetime, timedelta
from secrets import token_hex
from unittest.mock import patch

import jwt as pyjwt
from django.core.cache import cache
from django.test import TestCase, override_settings
from graphql_jwt.settings import jwt_settings

from core.apps import CoreConfig
from core.auth import decode
from core.auth import revocation
from core.auth.claims import claims_from_payload, issued_at_from
from core.models import InteractiveUser, User
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import (
    create_test_interactive_user,
    create_test_role,
    create_test_technical_user,
)

DEPLOYMENT_KID = "deployment-2026-09"
DEPLOYMENT_KEY = token_hex(32)

with_deployment_key = override_settings(
    JWT_DEPLOYMENT_KEYS={DEPLOYMENT_KID: DEPLOYMENT_KEY},
    JWT_DEPLOYMENT_ALGORITHM="HS256",
)


def _password():
    """Generated, so no password-shaped literal ends up in the repository."""
    return token_hex(16) + "Aa1!"


def _now():
    return timegm(datetime.utcnow().utctimetuple())


def _exp(days=1):
    return timegm((datetime.utcnow() + timedelta(days=days)).utctimetuple())


def _sign(username, issued_at=None, **claims):
    """A deployment-key token, so its signature survives a salt rotation and the
    not-before is the only thing that can reject it.
    """
    payload = {"username": username, "exp": _exp(), **claims}
    if issued_at is not None:
        payload["iat"] = issued_at
    return pyjwt.encode(
        payload, DEPLOYMENT_KEY, algorithm="HS256", headers={"kid": DEPLOYMENT_KID}
    )


def _stored_not_before(user):
    """Read it back from the database, not from the in-memory instance."""
    return (
        User.objects.values_list("i_user__json_ext", flat=True)
        .filter(username=user.username)
        .first()
        or {}
    ).get(revocation.NOT_BEFORE_KEY)


def _clear_not_before(user):
    """Creating a user sets a password, which stamps a not-before. Clear it to
    get the state of a user who has never had one.
    """
    InteractiveUser.objects.all().filter(pk=user.i_user.pk).update(json_ext={})


def _set_not_before(user, value):
    json_ext = dict(user.i_user.json_ext or {})
    json_ext[revocation.NOT_BEFORE_KEY] = value
    # .all() first: it returns a plain QuerySet, so this is a real UPDATE even
    # in the test that turns CachedManager on.
    InteractiveUser.objects.all().filter(pk=user.i_user.pk).update(json_ext=json_ext)


class IssueTimeContractTest(TestCase):
    """`assert_not_revoked` takes Claims, not a token, so these paths belong to
    any provider that builds one. LocalProvider requires iat and can no longer
    reach them, which is why they are exercised directly - through decode they
    would be answered by the require list and assert nothing.
    """

    def setUp(self):
        self.user = create_test_interactive_user(
            username="revokeClaims", password=_password()
        )

    def _claims(self, **payload):
        return claims_from_payload(
            {"username": "revokeClaims", "exp": _exp(), **payload}
        )

    def test_nbf_is_used_when_there_is_no_iat(self):
        _set_not_before(self.user, _now())

        with self.assertRaises(pyjwt.InvalidTokenError):
            revocation.assert_not_revoked(self._claims(nbf=_now() - 60))

    def test_orig_iat_is_used_when_there_is_neither_iat_nor_nbf(self):
        # graphql_jwt writes origIat whenever refresh is enabled, and a
        # refreshed token carries the original login time there.
        _set_not_before(self.user, _now())

        with self.assertRaises(pyjwt.InvalidTokenError):
            revocation.assert_not_revoked(self._claims(origIat=_now() - 60))

    def test_a_non_numeric_issue_time_fails_closed(self):
        # origIat is a graphql_jwt claim PyJWT does not validate, so a
        # non-numeric one arrives intact. It must fail as an invalid token, not
        # as the TypeError a bare comparison would raise.
        _set_not_before(self.user, _now())

        with self.assertRaises(pyjwt.InvalidTokenError):
            revocation.assert_not_revoked(self._claims(origIat="not-a-number"))

    def test_an_issue_time_after_the_not_before_passes(self):
        _set_not_before(self.user, _now() - 60)

        revocation.assert_not_revoked(self._claims(iat=_now()))


@with_deployment_key
class NotBeforeCheckTest(TestCase):
    """The check itself. Deployment-key tokens, so the per-user salt plays no
    part and only the not-before can reject them.
    """

    def setUp(self):
        self.user = create_test_interactive_user(
            username="revokeCheck", password=_password()
        )

    def test_token_issued_before_the_not_before_is_rejected(self):
        _set_not_before(self.user, _now())
        token = _sign("revokeCheck", issued_at=_now() - 60)

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)

    def test_token_issued_after_the_not_before_still_decodes(self):
        _set_not_before(self.user, _now() - 60)
        token = _sign("revokeCheck", issued_at=_now())

        self.assertEqual(decode(token)["username"], "revokeCheck")

    def test_user_with_no_not_before_is_unaffected(self):
        _clear_not_before(self.user)
        token = _sign("revokeCheck", issued_at=_now() - 3600)

        self.assertEqual(decode(token)["username"], "revokeCheck")

    def test_a_local_token_without_an_issue_time_never_reaches_the_check(self):
        # LocalProvider requires iat, so this shape is refused while the token
        # is still being verified. Asserted as that exact exception rather than
        # InvalidTokenError, which would also pass if the revocation check were
        # what rejected it - it is not, and cannot be.
        _set_not_before(self.user, _now())
        token = _sign("revokeCheck")

        with self.assertRaises(pyjwt.MissingRequiredClaimError):
            decode(token)

    def test_an_unusable_stored_not_before_is_read_as_absent(self):
        # Only the revocation module writes this key. If something else ever
        # puts a non-number there, the token is let through rather than locking
        # the user out of an account nobody revoked.
        _set_not_before(self.user, "not-a-number")
        token = _sign("revokeCheck", issued_at=_now() - 3600)

        self.assertEqual(decode(token)["username"], "revokeCheck")

    def test_technical_user_token_is_unaffected(self):
        # No interactive row, so no not-before can exist and nothing is
        # revoked. Issuing such a token still raises upstream; not fixed here.
        create_test_technical_user(username="revokeTech")
        token = _sign("revokeTech", issued_at=_now() - 3600)

        self.assertEqual(decode(token)["username"], "revokeTech")

    def test_unknown_user_is_not_revoked(self):
        token = _sign("noSuchUser", issued_at=_now() - 3600)

        self.assertEqual(decode(token)["username"], "noSuchUser")


class NotBeforeBumpTest(TestCase):
    """Where the revocation point moves, and where it must not."""

    def setUp(self):
        self.password = _password()
        self.user = create_test_interactive_user(
            username="revokeBump", password=self.password
        )

    def test_password_change_bumps_the_not_before(self):
        before = _now()
        self.user.i_user.set_password(_password())
        self.user.i_user.save()

        self.assertGreaterEqual(_stored_not_before(self.user), before)

    def test_password_change_through_the_service_bumps_it(self):
        from django.core.exceptions import ValidationError

        from core.services import change_user_password

        before = _now()
        try:
            change_user_password(
                self.user,
                username_to_update=None,
                old_password=self.password,
                new_password=_password(),
            )
        except ValidationError:
            # change_user_password saves the interactive user first, then raises
            # on the User row having no changed fields. Pre-existing defect,
            # reproduced on the base branch and unrelated to the not-before; the
            # bump is persisted by the save that already happened. Swallowed
            # rather than asserted so this test still passes once it is fixed.
            pass

        self.assertGreaterEqual(_stored_not_before(self.user), before)

    def test_role_change_does_not_bump_it_and_still_applies(self):
        # Rights are read from the DB per request, so a role edit already
        # applies immediately and must not end sessions.
        from core.services.userServices import create_or_update_user_roles

        _set_not_before(self.user, 1)
        role = create_test_role(
            perm_names=["gql_query_roles_perms"], name="revokeRoleProbe"
        )
        # self.user, not self.user.i_user: InteractiveUser.id_for_audit returns
        # the builtin `id` (core/models/user.py:295-296, a real bug). User's
        # returns i_user_id (:817-818).
        create_or_update_user_roles(
            self.user.i_user, [role.id], self.user.id_for_audit
        )

        self.assertEqual(_stored_not_before(self.user), 1)
        self.assertIn(
            int(CoreConfig.gql_query_roles_perms[0]),
            [int(right) for right in self.user.i_user.rights],
        )

    def test_disabling_a_user_bumps_the_not_before(self):
        from core.schema import set_user_deleted

        before = _now()
        set_user_deleted(self.user)

        self.assertGreaterEqual(_stored_not_before(self.user), before)

    def test_bump_never_moves_the_not_before_backwards(self):
        # Workers with disagreeing clocks must not be able to lower the bar and
        # bring already-rejected tokens back.
        future = _now() + 3600
        self.user.i_user.json_ext = {revocation.NOT_BEFORE_KEY: future}

        self.assertEqual(revocation.bump(self.user.i_user), future)
        self.assertEqual(
            self.user.i_user.json_ext[revocation.NOT_BEFORE_KEY], future
        )

    def test_bump_assigns_a_copy_rather_than_mutating_in_place(self):
        # Anything still holding the stored dict - a dirty-field snapshot, a
        # cached copy - must not see the new value before the save does.
        stored = {"default_rows_per_page": 20}
        self.user.i_user.json_ext = stored

        revocation.bump(self.user.i_user)

        self.assertNotIn(revocation.NOT_BEFORE_KEY, stored)
        self.assertEqual(
            self.user.i_user.json_ext["default_rows_per_page"], 20
        )

    def test_sign_out_everywhere_rejects_a_user_with_no_interactive_row(self):
        # A technical user has nowhere to store a not-before, so signing them
        # out has to fail loudly instead of quietly doing nothing.
        from django.core.exceptions import ValidationError

        from core.services import sign_out_everywhere

        technical = create_test_technical_user(username="revokeTechnical")
        core_user = User.objects.get(username=technical.username)

        with self.assertRaises(ValidationError):
            sign_out_everywhere(core_user)

    def test_sign_out_everywhere_bumps_the_not_before(self):
        from core.services import sign_out_everywhere

        before = _now()
        sign_out_everywhere(self.user)

        self.assertGreaterEqual(_stored_not_before(self.user), before)

    def test_sign_out_everywhere_needs_the_update_users_right_for_another_user(self):
        from rest_framework.exceptions import AuthenticationFailed

        from core.services import sign_out_everywhere

        # roles=[] stops the helper making this one an admin superuser, which is
        # what it does by default.
        nobody = create_test_interactive_user(
            username="revokeNobody", password=_password(), roles=[]
        )

        with self.assertRaises(AuthenticationFailed):
            sign_out_everywhere(nobody, username_to_sign_out=self.user.username)

    def test_an_administrator_can_sign_out_another_user(self):
        from core.services import sign_out_everywhere

        other = create_test_interactive_user(
            username="revokeOther", password=_password(), roles=[]
        )
        _set_not_before(other, 1)

        before = _now()
        sign_out_everywhere(self.user, username_to_sign_out=other.username)

        self.assertGreaterEqual(_stored_not_before(other), before)
        # The administrator's own sessions are untouched.
        self.assertLess(_stored_not_before(self.user), before + 1)


@with_deployment_key
class NotBeforeCacheTest(TestCase):
    """The object cache is off under tests (USE_CACHE = not IS_TESTING). Turn it
    on deliberately: LocMemCache is per-process, so a cached read would let a
    revoked token keep working on every worker but the one that revoked it.
    """

    def setUp(self):
        self.user = create_test_interactive_user(
            username="revokeCache", password=_password()
        )
        _clear_not_before(self.user)
        cache.clear()
        User.USE_CACHE = True
        InteractiveUser.USE_CACHE = True
        self.addCleanup(self._restore)

    @staticmethod
    def _restore():
        User.USE_CACHE = False
        InteractiveUser.USE_CACHE = False
        cache.clear()

    def test_the_not_before_is_read_from_the_database_not_the_cache(self):
        token = _sign("revokeCache", issued_at=_now() - 60)
        # Seed the cache with rows that carry no not-before, loaded past the
        # cache so they match what is really stored. CachedManager.filter() does
        # not populate on a miss - only .get() and save() do, through
        # update_cache() - so calling it directly is what a real request leaves
        # behind. The vector is User.get(username=...), whose CACHED_FK carries
        # i_user with it; a login_name lookup caches only the pk and so cannot
        # go stale.
        InteractiveUser.objects.all().filter(pk=self.user.i_user.pk).first(
        ).update_cache()
        User.objects.all().filter(pk=self.user.pk).first().update_cache()
        self.assertEqual(decode(token)["username"], "revokeCache")

        # Another process moves the revocation point. Nothing invalidates this
        # process's copy.
        _set_not_before(self.user, _now())

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)


@with_deployment_key
class StaleCopyWriteTest(TestCase):
    """Writes that start from this process's cached copy of the user, after
    another process has changed the row. Saving that copy whole would put the
    older values back.
    """

    def setUp(self):
        self.password = _password()
        self.user = create_test_interactive_user(
            username="revokeStale", password=self.password
        )
        cache.clear()
        User.USE_CACHE = True
        InteractiveUser.USE_CACHE = True
        self.addCleanup(NotBeforeCacheTest._restore)
        # Older than this second, so a bump is a real change: bumping to the
        # value already stored leaves nothing dirty, and save() then writes
        # nothing either way.
        _set_not_before(self.user, _now() - 600)
        # This process's copy, loaded past the cache so it matches the row, as
        # a request would leave it behind. See NotBeforeCacheTest.
        InteractiveUser.objects.all().filter(pk=self.user.i_user.pk).first(
        ).update_cache()
        User.objects.all().filter(pk=self.user.pk).first().update_cache()

    def _cached_user(self):
        return User.objects.get(username=self.user.username)

    def _change_password_elsewhere(self):
        """Change the stored password without touching this process's cache."""
        new_password = _password()
        detached = InteractiveUser.objects.all().get(pk=self.user.i_user.pk)
        detached.set_password(new_password)
        InteractiveUser.objects.all().filter(pk=detached.pk).update(
            password=detached.password, private_key=detached.private_key
        )
        return new_password

    def _stored_password_is(self, raw_password):
        stored = InteractiveUser.objects.all().get(pk=self.user.i_user.pk)
        return stored.check_password(raw_password)

    def test_issuing_a_token_keeps_a_revocation_point_set_elsewhere(self):
        from core.jwt import on_token_issued

        revoked_at = _now() + 3600
        _set_not_before(self.user, revoked_at)

        on_token_issued(sender=None, request=None, user=self._cached_user())

        self.assertEqual(_stored_not_before(self.user), revoked_at)

    def test_signing_out_never_lowers_a_revocation_point_set_elsewhere(self):
        from core.services import sign_out_everywhere

        revoked_at = _now() + 3600
        _set_not_before(self.user, revoked_at)

        sign_out_everywhere(self._cached_user())

        self.assertEqual(_stored_not_before(self.user), revoked_at)

    def test_signing_out_keeps_a_password_changed_elsewhere(self):
        from core.services import sign_out_everywhere

        new_password = self._change_password_elsewhere()

        sign_out_everywhere(self._cached_user())

        self.assertTrue(self._stored_password_is(new_password))

    def test_disabling_keeps_a_password_changed_elsewhere(self):
        from core.schema import set_user_deleted

        new_password = self._change_password_elsewhere()

        set_user_deleted(self._cached_user())

        self.assertTrue(self._stored_password_is(new_password))


class SignOutEverywhereMutationTest(openIMISGraphQLTestCase):
    """The GraphQL surface. The service behind it is covered above; what is left
    is the mutation's own authentication check, its payload, and the fact that a
    revoked token cannot be traded for a fresh one through refresh.
    """

    SIGN_OUT = """
        mutation {
            signOutEverywhere(input: {clientMutationId: "sign-out"}) {
                success
                error
            }
        }
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(
            username="revokeMutation", password=_password()
        )

    def test_signing_yourself_out_succeeds_and_moves_the_not_before(self):
        token = BaseTestContext(user=self.user).get_jwt()
        before = _now()

        response = self.query(
            self.SIGN_OUT, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
        )

        self.assertResponseNoErrors(response)
        payload = json.loads(response.content)["data"]["signOutEverywhere"]
        self.assertTrue(payload["success"], payload["error"])
        self.assertGreaterEqual(_stored_not_before(self.user), before)

    def test_a_token_older_than_the_sign_out_stops_working(self):
        # Signed the way the encoder signs today - the per-user salt, no kid -
        # so this goes through the real HTTP authentication path rather than
        # calling decode directly.
        #
        # Deliberately not the token that called the mutation. The check rejects
        # tokens issued strictly before the revocation point, and both happen
        # inside the same second here, so that one survives by design; see
        # test_a_token_issued_in_the_same_second_survives below.
        token = BaseTestContext(user=self.user).get_jwt()
        self.query(self.SIGN_OUT, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"})

        older = pyjwt.encode(
            {"username": self.user.username, "exp": _exp(), "nbf": _now() - 60},
            self.user.i_user.private_key,
            algorithm=jwt_settings.JWT_ALGORITHM,
        )
        response = self.client.get(
            "/api/core/users/current_user/", HTTP_AUTHORIZATION=f"Bearer {older}"
        )

        self.assertEqual(response.status_code, 401)

    def test_a_token_issued_after_the_sign_out_works(self):
        token = BaseTestContext(user=self.user).get_jwt()
        self.query(self.SIGN_OUT, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"})

        fresh = BaseTestContext(user=self.user).get_jwt()
        response = self.client.get(
            "/api/core/users/current_user/", HTTP_AUTHORIZATION=f"Bearer {fresh}"
        )

        self.assertEqual(response.status_code, 200)

    def test_a_token_issued_in_the_same_second_survives(self):
        # Documents an accepted limit rather than asserting a desirable one.
        # The stored point and the token's issue time are both whole seconds,
        # so a token minted in the same second as the sign-out is not strictly
        # older and is let through. Tightening the comparison would instead
        # reject the fresh token a user receives right after changing their own
        # password, which is the worse failure.
        token = BaseTestContext(user=self.user).get_jwt()
        # The same second by construction: a sign-out that happened to land in
        # the next second would make the token older and this test flaky. The
        # issue time is read the way the check reads it.
        issued = issued_at_from(pyjwt.decode(token, options={"verify_signature": False}))
        with patch.object(revocation, "_now", return_value=issued):
            signed_out = self.query(
                self.SIGN_OUT, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"}
            )
        payload = json.loads(signed_out.content)["data"]["signOutEverywhere"]
        self.assertTrue(payload["success"], payload["error"])
        self.assertEqual(_stored_not_before(self.user), issued)

        response = self.client.get(
            "/api/core/users/current_user/", HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        self.assertEqual(response.status_code, 200)

    def test_an_anonymous_caller_cannot_sign_anyone_out(self):
        response = self.query(self.SIGN_OUT)

        body = json.loads(response.content)
        payload = (body.get("data") or {}).get("signOutEverywhere")
        refused = "errors" in body or (payload and payload["success"] is False)
        self.assertTrue(refused, body)

    def test_a_revoked_token_cannot_be_refreshed(self):
        # Single-token refresh re-decodes what it is handed, so the revocation
        # check covers it and there is no way to mint a fresh token from a dead
        # one. This is the property that makes the check complete.
        #
        # Strictly older than the sign-out by construction, and valid until it:
        # a token minted in the same second would survive by design and prove
        # nothing either way.
        _set_not_before(self.user, _now() - 120)
        older = _sign(self.user.username, issued_at=_now() - 60, origIat=_now() - 60)
        with with_deployment_key:
            self.assertEqual(decode(older)["username"], self.user.username)

        token = BaseTestContext(user=self.user).get_jwt()
        self.query(self.SIGN_OUT, headers={"HTTP_AUTHORIZATION": f"Bearer {token}"})

        with with_deployment_key:
            response = self.query(
                """
                mutation refresh($token: String!) {
                    refreshToken(token: $token) { token }
                }
                """,
                variables={"token": older},
            )
            with self.assertRaises(pyjwt.InvalidTokenError):
                decode(older)

        self.assertIn("errors", json.loads(response.content))
