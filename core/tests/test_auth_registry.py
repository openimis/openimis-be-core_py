from calendar import timegm
from dataclasses import dataclass
from datetime import datetime, timedelta
from secrets import token_hex

import jwt as pyjwt
from django.test import TestCase, override_settings
from graphql_jwt.shortcuts import get_token

from core.auth import decode
from core.auth.claims import Claims
from core.auth.providers.base import IdentityProvider
from core.auth.providers.legacy import LegacyUserKeyProvider
from core.auth.registry import resolve
from core.models import User
from core.test_helpers import create_test_interactive_user

STUB_ISSUER = "https://idp.example.test/realms/openimis"
STUB_KEY = token_hex(32)


@dataclass
class DummyContext:
    user: User


class StubProvider(IdentityProvider):
    """A second provider, registered by dotted path from the test settings.

    It shares no key material and no code with the local path - which is the
    point: if this routes and verifies, an OpenID Connect provider can be added
    later without touching local tokens.
    """

    id = "stub"
    provision = "first_login"
    verify_calls = 0

    def accepts(self, header, unverified):
        return unverified.get("iss") == STUB_ISSUER

    def verify(self, token):
        type(self).verify_calls += 1
        payload = pyjwt.decode(
            token, STUB_KEY, algorithms=["HS256"], issuer=STUB_ISSUER
        )
        return Claims(
            raw=payload,
            issuer=payload["iss"],
            subject=payload["sub"],
            username=payload["sub"],
            issued_at=payload.get("iat"),
            expires_at=payload["exp"],
        )


with_stub_provider = override_settings(
    AUTH_TOKEN_PROVIDERS=["core.tests.test_auth_registry.StubProvider"]
)


def _exp(days=1):
    return timegm((datetime.utcnow() + timedelta(days=days)).utctimetuple())


def _stub_token(subject="federatedUser"):
    return pyjwt.encode(
        {"iss": STUB_ISSUER, "sub": subject, "exp": _exp()}, STUB_KEY, algorithm="HS256"
    )


class ProviderRoutingTest(TestCase):
    def setUp(self):
        StubProvider.verify_calls = 0
        self.password = token_hex(16) + "Aa1!"
        self.user = create_test_interactive_user(
            username="authRouting", password=self.password
        )
        self.local_token = get_token(self.user, DummyContext(user=self.user))

    def test_unknown_issuer_is_rejected(self):
        token = pyjwt.encode(
            {"iss": "https://elsewhere.example.test", "username": "x", "exp": _exp()},
            token_hex(32),
            algorithm="HS256",
        )

        with self.assertRaises(pyjwt.InvalidIssuerError):
            resolve(token)

    def test_local_token_routes_to_the_legacy_provider(self):
        self.assertIsInstance(resolve(self.local_token), LegacyUserKeyProvider)

    @with_stub_provider
    def test_registered_provider_handles_its_own_issuer(self):
        payload = decode(_stub_token())

        self.assertEqual(payload["sub"], "federatedUser")
        self.assertEqual(StubProvider.verify_calls, 1)

    @with_stub_provider
    def test_local_tokens_never_reach_a_foreign_provider(self):
        decode(self.local_token)

        self.assertEqual(StubProvider.verify_calls, 0)

    def test_provider_registration_follows_the_settings(self):
        # The registry caches its provider list; the cache key has to include
        # the registration setting or override_settings would be defeated.
        with with_stub_provider:
            self.assertEqual(resolve(_stub_token()).id, "stub")

        with self.assertRaises(pyjwt.InvalidIssuerError):
            resolve(_stub_token())
