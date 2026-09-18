import json
from hashlib import sha256
from secrets import token_hex

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from core.apps import CoreConfig
from core.auth import passwords
from core.models import ModuleConfiguration


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

    def test_saving_the_row_applies_the_hasher_without_a_restart(self):
        self.configure(passwords.ARGON2)
        with self.captureOnCommitCallbacks(execute=True):
            _row(password_hasher=passwords.SHA256).save()
        self.assertEqual(CoreConfig.password_hasher, passwords.SHA256)
