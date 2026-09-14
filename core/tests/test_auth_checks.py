from secrets import token_hex

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase, override_settings

from core.auth import checks


def _keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem(private_key):
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


SIGNING_KEY = _keypair()
SIGNING_PEM = _pem(SIGNING_KEY)


class SigningKeyCheckTest(TestCase):
    """`core.auth.E001` - the deployment keypair is the only thing that signs,
    so an unprovisioned deployment is a startup failure, not a first-login one.
    """

    @override_settings(JWT_SIGNING_KEY=None)
    def test_nothing_provisioned_is_an_error(self):
        errors = checks.signing_key_is_provisioned(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E001"])
        self.assertIn("JWT_SIGNING_KEY", errors[0].msg)

    @override_settings(JWT_SIGNING_KEY=SIGNING_PEM)
    def test_a_provisioned_key_passes(self):
        self.assertEqual(checks.signing_key_is_provisioned(None), [])

    @override_settings(JWT_SIGNING_KEY="-----BEGIN PRIVATE KEY-----\nnope\n")
    def test_unparseable_material_is_reported_not_raised(self):
        # keys.signing_key() raises ValueError, and Django does not catch
        # exceptions from checks - without the catch the operator gets a
        # traceback instead of the check that explains it.
        errors = checks.signing_key_is_provisioned(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E001"])
        self.assertIn("JWT_SIGNING_KEY", errors[0].msg)

    @override_settings(JWT_SIGNING_KEY="/nonexistent/jwt_signing_key.pem")
    def test_an_unreadable_path_is_reported_not_raised(self):
        errors = checks.signing_key_is_provisioned(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E001"])


@override_settings(JWT_SIGNING_KEY=SIGNING_PEM)
class DeploymentKeysCheckTest(TestCase):
    """`core.auth.W001` - the JWKS view skips what it cannot publish, silently
    and on every request. Saying so once at startup is where it belongs.
    """

    def test_a_publishable_key_set_passes(self):
        public_pem = SIGNING_KEY.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        with override_settings(JWT_DEPLOYMENT_KEYS={"retiring": public_pem}):
            self.assertEqual(checks.deployment_keys_are_publishable(None), [])

    def test_a_symmetric_entry_warns_and_names_its_kid(self):
        with override_settings(JWT_DEPLOYMENT_KEYS={"shared": token_hex(32)}):
            warnings = checks.deployment_keys_are_publishable(None)

        self.assertEqual([warning.id for warning in warnings], ["core.auth.W001"])
        self.assertIn("shared", warnings[0].msg)

    def test_nothing_configured_passes(self):
        with override_settings(JWT_DEPLOYMENT_KEYS=None):
            self.assertEqual(checks.deployment_keys_are_publishable(None), [])
