from secrets import token_hex

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.auth import keys

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


@with_signing_key
class ProvisionedKeyTest(TestCase):
    def test_publishes_the_provisioned_key_under_its_kid(self):
        response = APIClient().get(JWKS_URL)
        published = response.json()["keys"]

        self.assertEqual(len(published), 1)
        jwk = published[0]
        self.assertEqual(jwk["kid"], keys.signing_key()[1])
        self.assertEqual(jwk["kty"], "RSA")
        self.assertEqual(jwk["use"], "sig")
        self.assertEqual(jwk["alg"], keys.algorithm())
        self.assertTrue(jwk["n"] and jwk["e"])

    def test_never_publishes_the_private_half(self):
        jwk = APIClient().get(JWKS_URL).json()["keys"][0]

        # Asserted on the parsed members, not the raw body: base64 contains
        # these letters, so a substring search would pass for the wrong reason.
        self.assertEqual(set(jwk), {"kty", "n", "e", "kid", "use", "alg"})


class SymmetricKeyTest(TestCase):
    """`JWT_DEPLOYMENT_KEYS` is a plain settings dict and core's own suite puts
    an HMAC secret in it. Publishing one would turn the shared secret this work
    exists to remove into a one-request disclosure.
    """

    def test_a_symmetric_entry_is_not_published(self):
        secret = token_hex(32)
        with override_settings(
            JWT_SIGNING_KEY=SIGNING_PEM, JWT_DEPLOYMENT_KEYS={"legacy": secret}
        ):
            response = APIClient().get(JWKS_URL)
            expected_kid = keys.signing_key()[1]

        published = response.json()["keys"]
        self.assertEqual([jwk["kid"] for jwk in published], [expected_kid])
        self.assertNotIn(secret, response.content.decode())


@with_signing_key
class UnauthenticatedAccessTest(TestCase):
    def test_no_authorization_header_is_fine(self):
        self.assertEqual(APIClient().get(JWKS_URL).status_code, 200)

    def test_a_junk_bearer_token_does_not_make_it_401(self):
        # The regression this pins: JWTAuthentication is a DRF default, so
        # dropping authentication_classes([]) would turn a garbage header into a
        # 401 on an endpoint whose whole point is being reachable by anyone.
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")

        self.assertEqual(client.get(JWKS_URL).status_code, 200)
