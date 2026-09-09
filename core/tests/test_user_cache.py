"""The object cache is disabled under tests (USE_CACHE = not IS_TESTING), so the
cached authentication path is never exercised by the rest of the suite. These
tests turn it on deliberately.
"""
import re

from django.core.cache import cache
from django.db import connection

from core.models import User, InteractiveUser
from core.models.openimis_graphql_test_case import (
    openIMISGraphQLTestCase,
    BaseTestContext,
)
from core.test_helpers import create_test_interactive_user
from core.utils import get_cache_key

USER_TABLES = ("core_User", "tblUsers")


class UserCacheTestCase(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="cacheprobe")

    def setUp(self):
        super().setUp()
        # the class-level instance keeps whatever a sibling test wrote to it in
        # memory, even after the DB rolled back; start from what is really stored
        User.USE_CACHE = False
        InteractiveUser.USE_CACHE = False
        cache.clear()
        self.user = User.objects.get(username="cacheprobe")
        User.USE_CACHE = True
        InteractiveUser.USE_CACHE = True
        self.addCleanup(self._restore)

    @staticmethod
    def _restore():
        User.USE_CACHE = False
        InteractiveUser.USE_CACHE = False
        cache.clear()

    def _get_current_user(self, token):
        """Return (response, number of queries against the user tables)."""
        seen = []

        def tracer(execute, sql, params, many, context):
            match = re.search(r'FROM "([^"]+)"', sql)
            if match and match.group(1) in USER_TABLES:
                seen.append(match.group(1))
            return execute(sql, params, many, context)

        with connection.execute_wrapper(tracer):
            response = self.client.get(
                "/api/core/users/current_user/",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
        return response, len(seen)

    def test_username_alias_is_written_to_the_cache(self):
        # update_cache() reads UNIQUE_FIELDS off the instance; without it on the
        # User model the alias is never written and every lookup misses
        User.objects.get(username=self.user.username)
        alias = cache.get(get_cache_key(User, self.user.username))
        self.assertIsNotNone(alias, "no cache alias written for the username")

    def test_repeated_authentication_stops_querying_the_user_tables(self):
        token = BaseTestContext(user=self.user).get_jwt()

        first, first_queries = self._get_current_user(token)
        self.assertEqual(first.status_code, 200)
        self.assertGreater(first_queries, 0, "the cold request should hit the database")

        # a couple of requests to let both the alias and the FK settle
        self._get_current_user(token)
        warm, warm_queries = self._get_current_user(token)

        self.assertEqual(warm.status_code, 200)
        self.assertEqual(
            warm_queries, 0, "a warm authentication must not query the user tables"
        )
        self.assertEqual(
            warm.json(), first.json(), "cached payload differs from the cold one"
        )

    def test_cached_interactive_user_keeps_the_fields_auth_depends_on(self):
        # jwt_decode_user_key reads i_user.private_key to verify the signature,
        # so the cached instance has to carry it
        i_user = self.user.i_user
        i_user.private_key = "a-private-signing-key"
        i_user.save()
        cache.clear()

        User.objects.get(username=self.user.username)  # populates the cache
        cached = User.objects.get(username=self.user.username)
        self.assertEqual(cached.i_user.private_key, "a-private-signing-key")
        self.assertEqual(cached.i_user.login_name, i_user.login_name)

    def test_authentication_works_for_a_user_with_a_private_key(self):
        i_user = self.user.i_user
        i_user.private_key = "another-private-signing-key"
        i_user.save()

        token = BaseTestContext(user=self.user).get_jwt()
        cold, _ = self._get_current_user(token)
        self.assertEqual(cold.status_code, 200)

        self._get_current_user(token)
        warm, _ = self._get_current_user(token)
        self.assertEqual(warm.status_code, 200)
        self.assertEqual(warm.json()["username"], self.user.username)
