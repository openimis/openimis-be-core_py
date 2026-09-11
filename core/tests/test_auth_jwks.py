import json
from dataclasses import dataclass
from secrets import token_hex

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase, override_settings
from graphql_jwt.shortcuts import get_token
from jwt.algorithms import RSAAlgorithm
from rest_framework.test import APIClient

from core.auth import keys
from core.models import User
from core.test_helpers import create_test_interactive_user

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


@override_settings(JWT_SIGNING_KEY=None, JWT_DEPLOYMENT_KEYS=None)
class EmptyKeySetTest(TestCase):
    """Nothing provisioned is a true answer, not an error: a consumer polling
    before provisioning must not have to special-case a 404.

    Both settings are overridden rather than assumed absent: JWT_SIGNING_KEY
    comes from the environment, so without this the test asserts against
    whatever the machine happens to have provisioned.
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


class PemVerificationKeyTest(TestCase):
    """A retiring public half is the documented rotation step, and a settings
    file naturally holds it as PEM text rather than a key object. PyJWT accepts
    both when verifying, so JWKS must publish both or a JWKS-only verifier
    cannot check tokens signed by the outgoing key.
    """

    def test_publishes_an_rsa_key_given_as_pem_text(self):
        retiring = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        retiring_pem = retiring.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        with override_settings(
            JWT_SIGNING_KEY=SIGNING_PEM,
            JWT_DEPLOYMENT_KEYS={"retiring": retiring_pem},
        ):
            response = APIClient().get(JWKS_URL)

        published = {jwk["kid"]: jwk for jwk in response.json()["keys"]}
        self.assertIn("retiring", published)
        self.assertEqual(published["retiring"]["kty"], "RSA")


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


@dataclass
class DummyContext:
    """graphql_jwt hands the encode handler a context; only .user is read."""

    user: User


@with_signing_key
class VerifyUsingOnlyTheEndpointTest(TestCase):
    """The ticket's done-when. Nothing below the fetch may touch settings or
    core.auth - reaching back into them would prove nothing about a third party
    holding no shared secret.
    """

    def test_a_token_openimis_issued_verifies_from_the_published_key(self):
        user = create_test_interactive_user(username="jwksVerifier")
        token = get_token(user, DummyContext(user=user))

        document = APIClient().get(JWKS_URL).json()

        kid = pyjwt.get_unverified_header(token)["kid"]
        jwk = next(k for k in document["keys"] if k["kid"] == kid)
        payload = pyjwt.decode(
            token,
            RSAAlgorithm.from_jwk(json.dumps(jwk)),
            algorithms=[jwk["alg"]],
            options={"verify_aud": False},
        )

        self.assertEqual(payload["username"], user.username)


@with_signing_key
class RendererTest(TestCase):
    def test_never_renders_the_browsable_html_page(self):
        # Without renderer_classes the DRF default set includes the browsable
        # API, so a browser Accept header turns a machine-readable endpoint into
        # an HTML page.
        response = APIClient().get(JWKS_URL, HTTP_ACCEPT="text/html")

        self.assertNotIn("text/html", response.headers.get("Content-Type", ""))
