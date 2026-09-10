from io import StringIO

from django.core.cache import caches
from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.cache_control import (
    UnknownCacheAliasError,
    flush_caches,
    get_configured_cache_aliases,
    resolve_cache_aliases,
)
from core.models import Language
from core.test_helpers import create_test_interactive_user


TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "core-flushcache-default",
        "KEY_PREFIX": "oi",
    },
    "location": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "core-flushcache-location",
        "KEY_PREFIX": "loc",
    },
    "coverage": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "core-flushcache-coverage",
        "KEY_PREFIX": "cov",
    },
}

TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


def _seed_caches():
    caches["default"].set("k-default", "v-default")
    caches["location"].set("k-location", "v-location")
    caches["coverage"].set("k-coverage", "v-coverage")


@override_settings(CACHES=TEST_CACHES)
class CacheControlTest(TestCase):
    def test_lists_configured_aliases_in_order(self):
        self.assertEqual(
            get_configured_cache_aliases(),
            ["default", "location", "coverage"],
        )

    def test_resolve_empty_means_all(self):
        self.assertEqual(
            resolve_cache_aliases(None),
            ["default", "location", "coverage"],
        )
        self.assertEqual(
            resolve_cache_aliases([]),
            ["default", "location", "coverage"],
        )

    def test_resolve_rejects_unknown_alias(self):
        with self.assertRaises(UnknownCacheAliasError) as cm:
            resolve_cache_aliases(["default", "missing"])
        self.assertIn("missing", str(cm.exception))

    def test_flush_all(self):
        _seed_caches()
        flushed, errors = flush_caches()
        self.assertEqual(flushed, ["default", "location", "coverage"])
        self.assertEqual(errors, [])
        self.assertIsNone(caches["default"].get("k-default"))
        self.assertIsNone(caches["location"].get("k-location"))
        self.assertIsNone(caches["coverage"].get("k-coverage"))

    def test_flush_individual_alias(self):
        _seed_caches()
        flushed, errors = flush_caches(["location"])
        self.assertEqual(flushed, ["location"])
        self.assertEqual(errors, [])
        self.assertEqual(caches["default"].get("k-default"), "v-default")
        self.assertIsNone(caches["location"].get("k-location"))
        self.assertEqual(caches["coverage"].get("k-coverage"), "v-coverage")

    def test_flush_subset(self):
        _seed_caches()
        flushed, errors = flush_caches(["default", "coverage"])
        self.assertEqual(flushed, ["default", "coverage"])
        self.assertEqual(errors, [])
        self.assertIsNone(caches["default"].get("k-default"))
        self.assertEqual(caches["location"].get("k-location"), "v-location")
        self.assertIsNone(caches["coverage"].get("k-coverage"))


@override_settings(CACHES=TEST_CACHES)
class FlushCacheCommandTest(TestCase):
    def test_command_is_served_from_core(self):
        self.assertEqual(get_commands()["flushcache"], "core")

    def test_flush_all(self):
        _seed_caches()
        out = StringIO()
        call_command("flushcache", stdout=out)
        self.assertIn("Flushed 3 caches", out.getvalue())
        self.assertIsNone(caches["default"].get("k-default"))
        self.assertIsNone(caches["location"].get("k-location"))
        self.assertIsNone(caches["coverage"].get("k-coverage"))

    def test_flush_positional_alias(self):
        _seed_caches()
        call_command("flushcache", "location", stdout=StringIO())
        self.assertEqual(caches["default"].get("k-default"), "v-default")
        self.assertIsNone(caches["location"].get("k-location"))
        self.assertEqual(caches["coverage"].get("k-coverage"), "v-coverage")

    def test_flush_alias_flag(self):
        _seed_caches()
        call_command(
            "flushcache",
            alias_flags=["default", "coverage"],
            stdout=StringIO(),
        )
        self.assertIsNone(caches["default"].get("k-default"))
        self.assertEqual(caches["location"].get("k-location"), "v-location")
        self.assertIsNone(caches["coverage"].get("k-coverage"))

    def test_unknown_alias_does_not_flush(self):
        _seed_caches()
        with self.assertRaises(CommandError) as cm:
            call_command("flushcache", "nope", stdout=StringIO())
        self.assertIn("nope", str(cm.exception))
        self.assertEqual(caches["default"].get("k-default"), "v-default")

    def test_list_does_not_flush(self):
        _seed_caches()
        out = StringIO()
        call_command("flushcache", list_caches=True, stdout=out)
        output = out.getvalue()
        self.assertIn("default", output)
        self.assertIn("location", output)
        self.assertEqual(caches["default"].get("k-default"), "v-default")


@override_settings(CACHES=TEST_CACHES, STORAGES=TEST_STORAGES)
class FlushCacheAdminTest(TestCase):
    def setUp(self):
        Language.objects.get_or_create(
            code="en",
            defaults={"name": "English", "sort_order": 1},
        )
        self.user = create_test_interactive_user(username="cacheadmin")
        self.client = Client()
        self.url = reverse("admin:core_cache_flush")

    def test_requires_staff(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_page_lists_aliases(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("default", content)
        self.assertIn("location", content)
        self.assertIn("coverage", content)
        self.assertIn("Flush selected", content)
        self.assertIn("Flush all", content)

    def test_flush_all_from_admin(self):
        _seed_caches()
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"action": "flush_all"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(caches["default"].get("k-default"))
        self.assertIsNone(caches["location"].get("k-location"))
        self.assertIsNone(caches["coverage"].get("k-coverage"))
        self.assertContains(response, "Flushed cache")

    def test_flush_selected_from_admin(self):
        _seed_caches()
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            {"action": "flush_selected", "aliases": ["location"]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(caches["default"].get("k-default"), "v-default")
        self.assertIsNone(caches["location"].get("k-location"))
        self.assertEqual(caches["coverage"].get("k-coverage"), "v-coverage")
        self.assertContains(response, "location")

    def test_flush_selected_without_aliases_leaves_caches(self):
        _seed_caches()
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            {"action": "flush_selected"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(caches["default"].get("k-default"), "v-default")
        self.assertContains(response, "Select at least one cache")

    def test_caches_link_on_admin_index(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Caches")
        self.assertContains(response, reverse("admin:core_cache_flush"))
