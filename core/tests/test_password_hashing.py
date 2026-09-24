import json
from hashlib import sha256
from secrets import token_hex

from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase, TestCase
from rest_framework.exceptions import AuthenticationFailed

from core.apps import CoreConfig
from core.auth import passwords, revocation
from core.models import InteractiveUser, ModuleConfiguration
from core.services import user_authentication
from core.test_helpers import create_test_interactive_user


def _password():
    """Generated, so no password-shaped literal ends up in the repository."""
    return token_hex(16) + "Aa1!"


def _legacy(raw, salt):
    """What the legacy application wrote: uppercase hex, salt appended."""
    return sha256(f"{raw}{salt}".encode()).hexdigest().upper()


def _row(**cfg):
    return ModuleConfiguration(
        module="core", layer="be", version="1", config=json.dumps(cfg)
    )


class _PinnedHasher:
    """Set the configured hasher for one test and put it back afterwards."""

    def setUp(self):
        super().setUp()
        self.addCleanup(
            setattr, CoreConfig, "password_hasher", CoreConfig.password_hasher
        )

    def configure(self, hasher):
        CoreConfig.password_hasher = hasher


class HashPasswordTest(_PinnedHasher, SimpleTestCase):
    def test_argon2_by_default(self):
        self.configure(passwords.ARGON2)
        encoded = passwords.hash_password(_password(), token_hex(128))
        self.assertTrue(encoded.startswith("argon2$argon2id$"))
        # StoredPassword is varchar(256); "no migration" is the premise.
        self.assertLessEqual(len(encoded), 256)

    def test_the_same_password_never_hashes_the_same_twice(self):
        self.configure(passwords.ARGON2)
        raw, salt = _password(), token_hex(128)
        self.assertNotEqual(
            passwords.hash_password(raw, salt), passwords.hash_password(raw, salt)
        )

    def test_the_legacy_format_under_sha256(self):
        self.configure(passwords.SHA256)
        raw, salt = _password(), token_hex(128)
        self.assertEqual(passwords.hash_password(raw, salt), _legacy(raw, salt))

    def test_trailing_whitespace_is_stripped_in_both_formats(self):
        # The legacy hasher stripped it. Keeping that under argon2 means the
        # rehash of a verified legacy password re-verifies with the same input.
        raw, salt = _password(), token_hex(128)
        self.configure(passwords.SHA256)
        self.assertEqual(passwords.hash_password(raw + "  ", salt), _legacy(raw, salt))
        self.configure(passwords.ARGON2)
        encoded = passwords.hash_password(raw + "  ", salt)
        self.assertTrue(passwords.verify(raw, encoded, salt).ok)


class VerifyTest(_PinnedHasher, SimpleTestCase):
    def test_an_argon2_row_verifies_without_a_rehash(self):
        self.configure(passwords.ARGON2)
        raw, salt = _password(), token_hex(128)
        encoded = passwords.hash_password(raw, salt)
        self.assertEqual(
            passwords.verify(raw, encoded, salt), passwords.Verification(True, False)
        )

    def test_a_legacy_row_verifies_and_asks_for_a_rehash(self):
        self.configure(passwords.ARGON2)
        raw, salt = _password(), token_hex(128)
        self.assertEqual(
            passwords.verify(raw, _legacy(raw, salt), salt),
            passwords.Verification(True, True),
        )

    def test_a_lowercase_legacy_digest_verifies_too(self):
        # hashlib writes lowercase, the legacy application uppercase; the old
        # check_password lowercased both sides.
        self.configure(passwords.ARGON2)
        raw, salt = _password(), token_hex(128)
        self.assertTrue(passwords.verify(raw, _legacy(raw, salt).lower(), salt).ok)

    def test_a_wrong_password_fails_and_never_asks_for_a_rehash(self):
        self.configure(passwords.ARGON2)
        raw, salt = _password(), token_hex(128)
        for encoded in (passwords.hash_password(raw, salt), _legacy(raw, salt)):
            with self.subTest(encoded=encoded[:8]):
                self.assertEqual(
                    passwords.verify(_password(), encoded, salt),
                    passwords.Verification(False, False),
                )

    def test_under_sha256_a_legacy_row_is_left_alone(self):
        self.configure(passwords.SHA256)
        raw, salt = _password(), token_hex(128)
        self.assertEqual(
            passwords.verify(raw, _legacy(raw, salt), salt),
            passwords.Verification(True, False),
        )

    def test_under_sha256_an_argon2_row_still_verifies(self):
        # Flipping the flag back must not lock out anyone hashed while it was on.
        raw, salt = _password(), token_hex(128)
        self.configure(passwords.ARGON2)
        encoded = passwords.hash_password(raw, salt)
        self.configure(passwords.SHA256)
        self.assertEqual(
            passwords.verify(raw, encoded, salt), passwords.Verification(True, False)
        )

    def test_the_locked_sentinel_and_empty_values_fail_quietly(self):
        self.configure(passwords.ARGON2)
        for encoded in (CoreConfig.locked_user_password_hash, "", None):
            with self.subTest(encoded=encoded):
                self.assertEqual(
                    passwords.verify(_password(), encoded, token_hex(128)),
                    passwords.Verification(False, False),
                )

    def test_a_malformed_argon2_string_fails_rather_than_raising(self):
        # A corrupt row is a failed login, not a 500.
        self.configure(passwords.ARGON2)
        self.assertEqual(
            passwords.verify(_password(), "argon2$argon2id$broken", token_hex(128)),
            passwords.Verification(False, False),
        )


class ConfigurationTest(_PinnedHasher, TestCase):
    def test_the_default_is_argon2(self):
        from core.apps import DEFAULT_CFG

        self.assertEqual(DEFAULT_CFG["password_hasher"], passwords.ARGON2)

    def test_a_row_naming_no_hasher_is_fine(self):
        _row(csrf_protect_login=False).clean()

    def test_both_hashers_are_accepted(self):
        for hasher in passwords.HASHERS:
            with self.subTest(hasher=hasher):
                _row(password_hasher=hasher).clean()

    def test_an_unknown_hasher_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            _row(password_hasher="bcrypt").clean()
        self.assertIn("config", caught.exception.message_dict)
        self.assertIn("bcrypt", str(caught.exception))

    def test_a_config_body_that_is_not_an_object_is_refused(self):
        # clean() guards JSON syntax but not shape, so a valid-JSON list reaches
        # this validator. Merging it over the defaults raises a TypeError that
        # start-up swallows, dropping the whole core configuration silently.
        row = ModuleConfiguration(
            module="core", layer="be", version="1", config="[1, 2]"
        )
        with self.assertRaises(ValidationError) as caught:
            row.clean()
        self.assertIn("config", caught.exception.message_dict)

    def test_an_unvalidated_hasher_value_falls_back_to_argon2(self):
        # A row written by a fixture or by direct SQL never reaches clean().
        self.configure("bcrypt")
        self.assertEqual(passwords.configured(), passwords.ARGON2)
        raw, salt = _password(), token_hex(128)
        self.assertTrue(passwords.hash_password(raw, salt).startswith("argon2$"))
        # And rewriting still happens, rather than being silently disabled.
        self.assertEqual(
            passwords.verify(raw, _legacy(raw, salt), salt),
            passwords.Verification(True, True),
        )

    def test_saving_the_row_applies_the_hasher_without_a_restart(self):
        self.configure(passwords.ARGON2)
        with self.captureOnCommitCallbacks(execute=True):
            _row(password_hasher=passwords.SHA256).save()
        self.assertEqual(CoreConfig.password_hasher, passwords.SHA256)


def _stored(user):
    """The row as the database holds it, not the in-memory instance."""
    return (
        InteractiveUser.objects.all()
        .filter(pk=user.i_user.pk)
        .values("password", "private_key", "json_ext", "version")
        .get()
    )


def _make_legacy(user, raw):
    """Put the user back on the legacy format - the state an upgraded
    deployment finds every account in.

    .all() first: it returns a plain QuerySet, so this is a real UPDATE even
    with the model cache on.
    """
    salt = _stored(user)["private_key"]
    InteractiveUser.objects.all().filter(pk=user.i_user.pk).update(
        password=_legacy(raw, salt)
    )
    user.i_user.refresh_from_db()


def _not_before(row):
    return (row["json_ext"] or {}).get(revocation.NOT_BEFORE_KEY)


class InteractiveUserPasswordTest(_PinnedHasher, TestCase):
    def setUp(self):
        super().setUp()
        self.configure(passwords.ARGON2)
        self.raw = _password()
        self.user = create_test_interactive_user(
            username="argon2_" + token_hex(4), password=self.raw
        )

    def test_set_password_writes_argon2_and_still_mints_a_salt(self):
        row = _stored(self.user)
        self.assertTrue(row["password"].startswith("argon2$"))
        self.assertTrue(row["private_key"])

    def test_set_password_writes_the_legacy_format_under_sha256(self):
        self.configure(passwords.SHA256)
        self.user.i_user.set_password(self.raw)
        self.user.i_user.save()
        row = _stored(self.user)
        self.assertEqual(row["password"], _legacy(self.raw, row["private_key"]))

    def test_the_check_that_verifies_a_legacy_row_rewrites_it(self):
        _make_legacy(self.user, self.raw)
        before = _stored(self.user)

        self.assertTrue(self.user.i_user.check_password(self.raw))

        after = _stored(self.user)
        self.assertTrue(after["password"].startswith("argon2$"))
        # Only the hash moved. The version is untouched too: re-encoding a
        # password is not a change to the credential.
        self.assertEqual(after["private_key"], before["private_key"])
        self.assertEqual(_not_before(after), _not_before(before))
        self.assertEqual(after["version"], before["version"])
        # And the rewritten row verifies on its own, without a second rewrite.
        self.assertTrue(self.user.i_user.check_password(self.raw))
        self.assertEqual(_stored(self.user), after)

    def test_a_wrong_password_leaves_a_legacy_row_alone(self):
        _make_legacy(self.user, self.raw)
        before = _stored(self.user)
        self.assertFalse(self.user.i_user.check_password(_password()))
        self.assertEqual(_stored(self.user), before)

    def test_under_sha256_a_verified_legacy_row_is_left_alone(self):
        _make_legacy(self.user, self.raw)
        self.configure(passwords.SHA256)
        before = _stored(self.user)
        self.assertTrue(self.user.i_user.check_password(self.raw))
        self.assertEqual(_stored(self.user), before)

    def test_an_unsaved_instance_is_not_written_by_a_check(self):
        salt = token_hex(128)
        fresh = InteractiveUser(
            login_name="never_saved", private_key=salt, password=_legacy(self.raw, salt)
        )
        self.assertTrue(fresh.check_password(self.raw))
        self.assertTrue(fresh.password.startswith("argon2$"))
        self.assertIsNone(fresh.pk)
        self.assertFalse(
            InteractiveUser.objects.filter(login_name="never_saved").exists()
        )

    def test_the_rehash_writes_only_the_hash(self):
        """A stale in-memory row must not put its other columns back.

        On the authentication path the instance can come from the per-process
        object cache, so anything another worker wrote meanwhile is newer than
        what this instance holds. The revocation point is the one that matters:
        putting an old value back would revive sessions someone had ended.
        """
        _make_legacy(self.user, self.raw)
        stale = InteractiveUser.objects.all().get(pk=self.user.i_user.pk)
        revoked_at = 4102444800
        InteractiveUser.objects.all().filter(pk=stale.pk).update(
            json_ext={revocation.NOT_BEFORE_KEY: revoked_at}
        )

        self.assertTrue(stale.check_password(self.raw))

        row = _stored(self.user)
        self.assertTrue(row["password"].startswith("argon2$"))
        self.assertEqual(_not_before(row), revoked_at)

    def test_a_password_changed_meanwhile_is_not_replaced(self):
        """The rehash only replaces the hash it verified. A change committed
        between the check and the write - by another worker, or through the
        object cache's older copy - keeps the new password."""
        _make_legacy(self.user, self.raw)
        stale = InteractiveUser.objects.all().get(pk=self.user.i_user.pk)
        new_raw = _password()
        changed = InteractiveUser.objects.all().get(pk=stale.pk)
        changed.set_password(new_raw)
        changed.save()

        self.assertTrue(stale.check_password(self.raw))

        current = InteractiveUser.objects.all().get(pk=stale.pk)
        self.assertTrue(current.check_password(new_raw))
        self.assertFalse(current.check_password(self.raw))

    def test_the_login_flow_rehashes(self):
        # authenticate() -> ModelBackend -> User.check_password -> i_user: the
        # path the GraphQL login, the REST login and HTTP Basic all take.
        _make_legacy(self.user, self.raw)
        user = user_authentication(
            RequestFactory().post("/"), self.user.username, self.raw
        )
        self.assertEqual(user.pk, self.user.pk)
        self.assertTrue(_stored(self.user)["password"].startswith("argon2$"))

    def test_the_login_flow_refuses_a_wrong_password_and_leaves_the_row(self):
        _make_legacy(self.user, self.raw)
        before = _stored(self.user)
        with self.assertRaises(AuthenticationFailed):
            user_authentication(
                RequestFactory().post("/"), self.user.username, _password()
            )
        self.assertEqual(_stored(self.user), before)
