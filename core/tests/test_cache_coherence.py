"""
OP-3281: per-user permission sets cached with no expiry, and a process-local
cache trusted while writes happen in another process (the Celery worker that
runs async mutations) - the individual import then rejected villages the user
was allowed (UAT OCM-1128).
"""
import time
from unittest import mock

from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

import core
from core import cache_control
from core.utils import clear_access_cache

LOCMEM = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "op3281"},
}
SHARED = {
    # never connected to: coherence is decided from the configuration alone
    "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://127.0.0.1:6399/0"},
}


def async_mutations(enabled):
    return mock.patch.object(core, "async_mutations", enabled, create=True)


class CacheIsCoherentTest(SimpleTestCase):
    def test_process_local_cache_is_coherent_only_without_async(self):
        cases = [
            (LOCMEM, False, True),
            (LOCMEM, True, False),
            (SHARED, False, True),
            (SHARED, True, True),
        ]
        for conf, is_async, expected in cases:
            with self.subTest(backend=conf["default"]["BACKEND"], is_async=is_async), \
                    override_settings(CACHES=conf), async_mutations(is_async):
                self.assertEqual(cache_control.cache_is_coherent("default"), expected)


@override_settings(CACHES=LOCMEM, CACHE_OBJECT_TTL=1234)
class DefaultTtlTest(SimpleTestCase):
    def setUp(self):
        caches["default"].clear()
        clear_access_cache()

    def _expires_in(self, key):
        backend = caches["default"]
        expiry = backend._expire_info.get(backend.make_key(key))
        return None if expiry is None else expiry - time.time()

    def test_overall_ttl_applies_when_no_timeout_is_given(self):
        with async_mutations(False):
            cache_control.cache_set("op3281_plain", 1)
        self.assertAlmostEqual(self._expires_in("op3281_plain"), 1234, delta=5)

    def test_no_entry_lives_forever(self):
        with async_mutations(False):
            cache_control.cache_set("op3281_none", 1, timeout=None)
            cache_control.set_user_rights(42, [101])
        self.assertAlmostEqual(self._expires_in("op3281_none"), 1234, delta=5)
        self.assertAlmostEqual(self._expires_in("rights_42"), 1234, delta=5)

    def test_explicit_timeout_is_kept(self):
        with async_mutations(False):
            cache_control.cache_set("op3281_short", 1, timeout=60)
        self.assertAlmostEqual(self._expires_in("op3281_short"), 60, delta=5)


@override_settings(CACHES=LOCMEM)
class IncoherentCacheTest(SimpleTestCase):
    """A process-local cache with async mutations: values live for one request only."""

    def setUp(self):
        caches["default"].clear()
        clear_access_cache()

    def test_value_is_kept_for_the_request_but_not_stored_in_the_backend(self):
        with async_mutations(True):
            cache_control.set_user_rights(42, [101, 102])
            self.assertEqual(cache_control.get_user_rights(42), [101, 102])
            self.assertIsNone(caches["default"].get("rights_42"))

            clear_access_cache()  # the next request
            self.assertIsNone(cache_control.get_user_rights(42))

    def test_invalidation_drops_the_request_value(self):
        with async_mutations(True):
            cache_control.set_user_rights(42, [101])
            cache_control.invalidate_user_rights(42)
            self.assertIsNone(cache_control.get_user_rights(42))

    def test_value_does_not_survive_a_celery_task_boundary(self):
        from celery.signals import task_prerun

        with async_mutations(True):
            cache_control.set_officer_flag("eo1", True)
            task_prerun.send(sender=None, task_id="op3281", task=None, args=(), kwargs={})
            self.assertIsNone(cache_control.get_officer_flag("eo1"))

    def test_named_alias_follows_its_own_backend(self):
        conf = {**LOCMEM, "location": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "op3281-loc"}}
        with override_settings(CACHES=conf), async_mutations(True):
            cache_control.cache_set("user_locations_7", [1, 2], alias="location")
            self.assertEqual(cache_control.cache_get("user_locations_7", alias="location"), [1, 2])
            self.assertIsNone(caches["location"].get("user_locations_7"))
