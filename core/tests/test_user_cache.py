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

    def test_repeated_authentication_queries_the_user_tables_once(self):
        # Warm authentication used to reach zero. It is one now: the token
        # revocation check reads the per-user not-before straight from the
        # database on every request, deliberately past this cache, because the
        # cache is per-process and a cached read would leave a revoked token
        # working on every worker but the one that revoked it. Everything else
        # authentication needs still comes from the cache.
        token = BaseTestContext(user=self.user).get_jwt()

        first, first_queries = self._get_current_user(token)
        self.assertEqual(first.status_code, 200)
        self.assertGreater(first_queries, 1, "the cold request should hit the database")

        # a couple of requests to let both the alias and the FK settle
        self._get_current_user(token)
        warm, warm_queries = self._get_current_user(token)

        self.assertEqual(warm.status_code, 200)
        self.assertEqual(
            warm_queries,
            1,
            "a warm authentication must query the user tables only for the "
            "revocation not-before",
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


class CachedForeignKeyBatchTestCase(openIMISGraphQLTestCase):
    """A page of cached objects must not resolve its FKs one row at a time."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users = [
            create_test_interactive_user(username=f"fkbatch{i}") for i in range(6)
        ]

    def setUp(self):
        super().setUp()
        User.USE_CACHE = True
        InteractiveUser.USE_CACHE = True
        cache.clear()
        self.addCleanup(self._restore)

    @staticmethod
    def _restore():
        User.USE_CACHE = False
        InteractiveUser.USE_CACHE = False
        cache.clear()

    def _fetch(self, ids):
        """Load the users and touch i_user on each, as a serializer would."""
        seen = []

        def tracer(execute, sql, params, many, context):
            match = re.search(r'FROM "([^"]+)"', sql)
            if match and match.group(1) in USER_TABLES:
                seen.append(match.group(1))
            return execute(sql, params, many, context)

        with connection.execute_wrapper(tracer):
            users = list(User.objects.filter(id__in=ids))
            names = [u.i_user.login_name if u.i_user else None for u in users]
        return names, len(seen)

    def test_a_page_of_cached_users_costs_at_most_one_query(self):
        ids = [u.id for u in self.users]

        cold_names, _ = self._fetch(ids)
        self._fetch(ids)  # let both caches settle
        warm_names, warm_queries = self._fetch(ids)

        self.assertLessEqual(
            warm_queries,
            1,
            "resolving the i_user of %d cached users took %d queries -- the "
            "foreign keys are being fetched one row at a time"
            % (len(ids), warm_queries),
        )
        self.assertEqual(set(cold_names), set(warm_names))
        self.assertEqual(len(warm_names), len(ids))
        self.assertNotIn(None, warm_names)
