import tempfile
from calendar import timegm
from dataclasses import dataclass
from datetime import datetime
from secrets import token_hex

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from django.test import TestCase, override_settings
from graphql_jwt.shortcuts import get_token

from core.auth import decode, keys
from core.auth.encode import encode as auth_encode
from core.models import User
from core.test_helpers import create_test_interactive_user


def _keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem(private_key):
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


# 2048 keeps the suite fast; the size is irrelevant to what is asserted.
SIGNING_KEY = _keypair()
SIGNING_PEM = _pem(SIGNING_KEY)
OTHER_PEM = _pem(_keypair())

with_signing_key = override_settings(JWT_SIGNING_KEY=SIGNING_PEM)


@dataclass
class DummyContext:
    """graphql_jwt hands the encode handler a context; only .user is read."""

    user: User


def _password():
    """Generated, so no password-shaped literal ends up in the repository."""
    return token_hex(16) + "Aa1!"


def _now():
    return timegm(datetime.utcnow().utctimetuple())


def _user(username):
    return create_test_interactive_user(username=username, password=_password())


def _issue(user):
    """Through graphql_jwt, so the test exercises the configured handler."""
    return get_token(user, DummyContext(user=user))


class NoKeyProvisionedTest(TestCase):
    """Nothing provisioned: every deployment today, and every deployment that
    upgrades without provisioning a key.
    """

    def test_tokens_carry_no_kid_and_are_signed_hs256(self):
        header = pyjwt.get_unverified_header(_issue(_user("signDefault")))

        self.assertIsNone(header.get("kid"))
        self.assertEqual(header["alg"], "HS256")

    def test_token_still_decodes(self):
        user = _user("signDefaultDecode")

        self.assertEqual(decode(_issue(user))["username"], user.username)

    def test_iat_is_emitted(self):
        # On this path too, not only in deployment mode: OP-3128's revocation
        # reference compares against it.
        payload = decode(_issue(_user("signDefaultIat")))

        self.assertIsInstance(payload["iat"], int)


@with_signing_key
class ProvisionedKeyTest(TestCase):
    def test_tokens_carry_the_derived_kid_and_are_signed_rs256(self):
        header = pyjwt.get_unverified_header(_issue(_user("signDeployment")))

        self.assertEqual(header["alg"], "RS256")
        self.assertEqual(header["kid"], keys.derive_kid(SIGNING_KEY.public_key()))

    def test_token_decodes_without_touching_the_database(self):
        token = _issue(_user("signDeploymentDecode"))

        with self.assertNumQueries(0):
            payload = decode(token)

        self.assertEqual(payload["username"], "signDeploymentDecode")

    def test_token_verifies_against_the_public_half(self):
        token = _issue(_user("signDeploymentVerify"))

        payload = pyjwt.decode(
            token, SIGNING_KEY.public_key(), algorithms=["RS256"]
        )

        self.assertEqual(payload["username"], "signDeploymentVerify")

    def test_iat_is_a_real_issue_time(self):
        # Not compared against nbf: both are the same instant at issue.
        payload = decode(_issue(_user("signDeploymentIat")))

        self.assertIsInstance(payload["iat"], int)
        self.assertLessEqual(abs(payload["iat"] - _now()), 5)

    def test_the_signing_key_is_also_a_verification_key(self):
        # Or a deployment provisions a key it cannot verify.
        kid = keys.derive_kid(SIGNING_KEY.public_key())

        self.assertIn(kid, keys.deployment_keys())


class MigrationWindowTest(TestCase):
    """The acceptance criterion the dual-shape decode exists for: provisioning
    a key must not log anyone out.
    """

    def test_a_token_issued_before_the_switch_still_decodes_after_it(self):
        user = _user("signMigration")
        legacy_token = _issue(user)

        with with_signing_key:
            self.assertEqual(decode(legacy_token)["username"], user.username)

    def test_both_shapes_decode_while_the_key_is_provisioned(self):
        legacy_user = _user("signMigrationLegacy")
        legacy_token = _issue(legacy_user)

        with with_signing_key:
            new_token = _issue(_user("signMigrationNew"))

            self.assertEqual(decode(legacy_token)["username"], legacy_user.username)
            self.assertEqual(decode(new_token)["username"], "signMigrationNew")

    def test_backing_the_key_out_needs_its_public_half_kept(self):
        # Unprovisioning takes the verification key with it, so the public half
        # has to reach JWT_DEPLOYMENT_KEYS first or outstanding tokens stop
        # verifying. The mode used to make this a one-setting rollback.
        with with_signing_key:
            token = _issue(_user("signRollback"))

        with self.assertRaises(pyjwt.InvalidTokenError):
            decode(token)

        kid = keys.derive_kid(SIGNING_KEY.public_key())
        with override_settings(JWT_DEPLOYMENT_KEYS={kid: SIGNING_KEY.public_key()}):
            self.assertEqual(decode(token)["username"], "signRollback")


class KeyIdDerivationTest(TestCase):
    """The kid is what makes replicas agree without shared state."""

    def test_the_same_key_yields_the_same_kid(self):
        reloaded = serialization.load_pem_private_key(
            SIGNING_PEM.encode(), password=None
        )

        self.assertEqual(
            keys.derive_kid(SIGNING_KEY.public_key()),
            keys.derive_kid(reloaded.public_key()),
        )

    def test_a_different_key_yields_a_different_kid(self):
        other = serialization.load_pem_private_key(OTHER_PEM.encode(), password=None)

        self.assertNotEqual(
            keys.derive_kid(SIGNING_KEY.public_key()),
            keys.derive_kid(other.public_key()),
        )

    def test_the_kid_is_a_base64url_thumbprint_with_no_padding(self):
        kid = keys.derive_kid(SIGNING_KEY.public_key())

        # SHA-256 in base64url, padding stripped.
        self.assertEqual(len(kid), 43)
        self.assertNotIn("=", kid)


class KeyLoadingTest(TestCase):
    """Provisioned as a mounted file or as an inline PEM - one setting, because
    OP-3131 has one environment variable to map onto it.
    """

    def test_an_inline_pem_loads(self):
        with override_settings(JWT_SIGNING_KEY=SIGNING_PEM):
            _, kid = keys.signing_key()

        self.assertEqual(kid, keys.derive_kid(SIGNING_KEY.public_key()))

    def test_a_file_path_loads_to_the_same_kid(self):
        with tempfile.NamedTemporaryFile("w", suffix=".pem") as handle:
            handle.write(SIGNING_PEM)
            handle.flush()

            with override_settings(JWT_SIGNING_KEY=handle.name):
                _, kid = keys.signing_key()

        self.assertEqual(kid, keys.derive_kid(SIGNING_KEY.public_key()))

    def test_a_file_and_an_inline_pem_produce_interchangeable_tokens(self):
        user = _user("signBothRoutes")

        with tempfile.NamedTemporaryFile("w", suffix=".pem") as handle:
            handle.write(SIGNING_PEM)
            handle.flush()

            with override_settings(JWT_SIGNING_KEY=handle.name):
                from_file = _issue(user)

        with with_signing_key:
            from_inline = _issue(user)

            # Decoded inside the block: outside it nothing is provisioned and
            # neither kid resolves, correctly so.
            self.assertEqual(decode(from_file)["username"], user.username)
            self.assertEqual(decode(from_inline)["username"], user.username)

        self.assertEqual(
            pyjwt.get_unverified_header(from_file)["kid"],
            pyjwt.get_unverified_header(from_inline)["kid"],
        )

    def test_nothing_provisioned_yields_no_signing_key(self):
        self.assertIsNone(keys.signing_key())

    def test_a_non_rsa_key_is_rejected_at_load(self):
        pem = ed25519.Ed25519PrivateKey.generate().private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        with override_settings(JWT_SIGNING_KEY=pem):
            with self.assertRaises(ValueError) as caught:
                keys.signing_key()

        self.assertIn("JWT_SIGNING_KEY", str(caught.exception))

    def test_unparseable_material_is_rejected_at_load(self):
        with override_settings(JWT_SIGNING_KEY="-----BEGIN PRIVATE KEY-----\nnope\n"):
            with self.assertRaises(ValueError) as caught:
                keys.signing_key()

        self.assertIn("JWT_SIGNING_KEY", str(caught.exception))


class EncodeWithoutAKeyTest(TestCase):
    """`jwt_encode_user_key` never reaches this with nothing provisioned, but
    an assembly can point JWT_ENCODE_HANDLER straight at `encode`.
    """

    def test_encoding_without_a_key_raises_and_names_the_setting(self):
        with self.assertRaises(ValueError) as caught:
            auth_encode({"username": "signNoKey", "exp": _now() + 3600})

        self.assertIn("JWT_SIGNING_KEY", str(caught.exception))


class CorruptSigningKeyTest(TestCase):
    """A signing key that will not parse is a server misconfiguration, so it
    surfaces as one.

    This is the deliberate exception to OP-3126 decision 6 - decode raising
    anything but an InvalidTokenError reaches the client as a 500. A 401 here
    would tell the client its token was bad when the deployment's key is, and
    would hide the outage.
    """

    @override_settings(JWT_SIGNING_KEY="-----BEGIN PRIVATE KEY-----\nnope\n")
    def test_a_kid_token_surfaces_the_misconfiguration_not_an_auth_failure(self):
        token = pyjwt.encode(
            {"username": "x", "exp": _now() + 3600},
            token_hex(32),
            algorithm="HS256",
            headers={"kid": "whatever"},
        )

        with self.assertRaises(ValueError) as caught:
            decode(token)

        self.assertNotIsInstance(caught.exception, pyjwt.InvalidTokenError)
        self.assertIn("JWT_SIGNING_KEY", str(caught.exception))

    @override_settings(JWT_SIGNING_KEY="-----BEGIN PRIVATE KEY-----\nnope\n")
    def test_issuing_refuses_rather_than_falling_back_to_the_per_user_key(self):
        # The operator set the variable, so they believe they are on the
        # deployment key. Issuing per-user tokens instead would hide that.
        user = _user("signCorruptIssue")

        with self.assertRaises(ValueError) as caught:
            _issue(user)

        self.assertIn("JWT_SIGNING_KEY", str(caught.exception))
