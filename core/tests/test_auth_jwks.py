from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

JWKS_URL = "/api/core/jwks.json"


def _pem(private_key):
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


# 2048 keeps the suite fast; the size is irrelevant to what is asserted.
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SIGNING_PEM = _pem(SIGNING_KEY)

with_signing_key = override_settings(JWT_SIGNING_KEY=SIGNING_PEM)


class EmptyKeySetTest(TestCase):
    """Nothing provisioned is a true answer, not an error: a consumer polling
    before provisioning must not have to special-case a 404.
    """

    def test_serves_an_empty_key_set(self):
        response = APIClient().get(JWKS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"keys": []})
