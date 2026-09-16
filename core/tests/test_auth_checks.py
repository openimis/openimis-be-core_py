from secrets import token_hex
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase, override_settings

from core.apps import CoreConfig
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
        # Django does not catch exceptions from checks, so without the catch the
        # operator gets a traceback instead of the check that explains it. E002,
        # not E001: silencing "not provisioned" must not also silence this.
        errors = checks.signing_key_is_provisioned(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E002"])
        self.assertIn("JWT_SIGNING_KEY", errors[0].msg)

    @override_settings(JWT_SIGNING_KEY="/nonexistent/jwt_signing_key.pem")
    def test_an_unreadable_path_is_reported_not_raised(self):
        errors = checks.signing_key_is_provisioned(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E002"])

    @override_settings(JWT_SIGNING_KEY=b"-----BEGIN PRIVATE KEY-----\nnope\n")
    def test_material_that_is_not_a_string_is_reported_not_raised(self):
        # keys._load tests "-----BEGIN" in material, which raises TypeError
        # rather than ValueError for bytes or a Path.
        errors = checks.signing_key_is_provisioned(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E002"])


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

    def test_a_setting_that_is_not_a_mapping_is_reported_not_raised(self):
        # A list reaches .items() and would otherwise raise AttributeError
        # inside the check, which is the traceback this module exists to avoid.
        with override_settings(JWT_DEPLOYMENT_KEYS=["kid1", "kid2"]):
            errors = checks.deployment_keys_are_publishable(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E003"])


class SecondFactorAppsCheckTest(TestCase):
    """`core.auth.E004` - core declares the django-otp dependency, but only the
    assembly can install its apps, so the two can drift apart."""

    def test_missing_second_factor_apps_are_reported(self):
        # Patching is_installed rather than override_settings(INSTALLED_APPS=...):
        # that override rebuilds the app registry, which re-runs CoreConfig.ready
        # and loses core's management-command registration for every test that
        # follows - three createsuperuser tests failed on it. The check reads
        # nothing but is_installed, so this is the whole seam.
        def installed(app):
            return app != "django_otp.plugins.otp_static"

        with patch.object(checks.django_apps, "is_installed", side_effect=installed):
            errors = checks.second_factor_apps_are_installed(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E004"])
        self.assertIn("otp_static", errors[0].msg)

    def test_installed_second_factor_apps_report_nothing(self):
        self.assertEqual(checks.second_factor_apps_are_installed(None), [])


class SecondFactorPolicyCheckTest(TestCase):
    """`core.auth.E005` - a policy value the predicate cannot act on, caught at
    startup rather than at the first login."""

    def test_an_unknown_policy_is_reported(self):
        with patch.object(CoreConfig, "second_factor_policy", "sometimes"):
            errors = checks.second_factor_policy_is_known(None)

        self.assertEqual([error.id for error in errors], ["core.auth.E005"])

    def test_a_known_policy_is_not(self):
        with patch.object(CoreConfig, "second_factor_policy", "per_role"):
            self.assertEqual(checks.second_factor_policy_is_known(None), [])
