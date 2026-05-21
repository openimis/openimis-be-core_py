from unittest.mock import MagicMock

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import User, TechnicalUser, InteractiveUser
from core.models.history_model import HistoryModel
from core.models.user import Language
from core.utils import get_cache_key


class UserTestCase(TestCase):

    def test_t_user_active_status(self):
        always_valid = User(
            username="always_valid", t_user=TechnicalUser(username="always_valid")
        )
        self.assertTrue(always_valid.is_active)

        import datetime

        not_yet_active = User(
            username="not_yet_active",
            t_user=TechnicalUser(
                username="not_yet_active",
                validity_from=datetime.datetime.now() + datetime.timedelta(days=1),
            ),
        )
        self.assertFalse(not_yet_active.is_active)

        not_active_anymore = User(
            username="not_active_anymore",
            t_user=TechnicalUser(
                username="not_active_anymore",
                validity_to=datetime.datetime.now() + datetime.timedelta(days=-1),
            ),
        )
        self.assertFalse(not_active_anymore.is_active)

    def test_interactive_user_bulk_operations_and_cache(self):
        """Test InteractiveUser.objects.bulk_create and bulk_update with cache functionality"""
        # Clear cache to ensure clean state
        cache.clear()

        # Get or create a language for testing
        language, _ = Language.objects.get_or_create(
            code="en",
            defaults={"name": "English", "sort_order": 1}
        )

        # Create test user for audit fields
        test_user = User.objects.create(
            username="test_admin",
        )

        # Test bulk_create
        users_to_create = [
            InteractiveUser(
                login_name=f"bulk_user_{i}",
                last_name=f"User{i}",
                other_names=f"Bulk{i}",
                language=language,
                email=f"user{i}@example.com"
            )
            for i in range(1, 4)
        ]

        # Perform bulk create
        InteractiveUser.USE_CACHE = True
        InteractiveUser.objects.bulk_create(users_to_create)

        # Retrieve created users from database
        created_users = []
        for i in range(1, 4):
            user = InteractiveUser.objects.get(login_name=f"bulk_user_{i}")
            created_users.append(user)

        # Verify users were created
        self.assertEqual(len(created_users), 3)
        for i, user in enumerate(created_users, 1):
            self.assertEqual(user.login_name, f"bulk_user_{i}")
            self.assertEqual(user.version, 1)

        # Verify cache was updated for created users
        for user in created_users:
            cache_key = get_cache_key(InteractiveUser, user.id)
            cached_data = cache.get(cache_key)
            self.assertIsNotNone(cached_data, f"Cache not updated for user {user.id}")
            self.assertEqual(cached_data['login_name'], user.login_name)

            # Check secondary cache (by login_name)
            secondary_cache_key = get_cache_key(InteractiveUser, user.login_name.lower())
            secondary_cached = cache.get(secondary_cache_key)
            self.assertIsNotNone(secondary_cached, f"Secondary cache not updated for user {user.login_name}")
            self.assertEqual(secondary_cached, user.id)

        # Test bulk_update
        users_to_update = created_users[:2]  # Update first 2 users
        update_fields = ['phone', 'email']

        # Modify fields
        for i, user in enumerate(users_to_update):
            user.phone = f"123-456-789{i}"
            user.email = f"updated_user{i}@example.com"

        # Perform bulk update
        InteractiveUser.objects.bulk_update(users_to_update, update_fields)

        # Refresh from database and verify updates
        for i, user in enumerate(users_to_update):
            user.refresh_from_db()
            self.assertEqual(user.phone, f"123-456-789{i}")
            self.assertEqual(user.email, f"updated_user{i}@example.com")
            self.assertEqual(user.version, 2)  # Version should be incremented

        # Verify cache was updated after bulk update
        for user in users_to_update:
            cache_key = get_cache_key(InteractiveUser, user.id)
            cached_data = cache.get(cache_key)
            self.assertIsNotNone(cached_data, f"Cache not updated after bulk update for user {user.id}")
            self.assertEqual(cached_data['phone'], user.phone)
            self.assertEqual(cached_data['email'], user.email)

        # Verify history was created
        for user in created_users:
            # Check that historical records exist
            historical_count = user.history.count()
            # Should have at least 1 historical record (creation)
            # and updated users should have 2 (creation + update)
            expected_history = 2 if user in users_to_update else 1
            self.assertEqual(
                historical_count, expected_history,
                f"User {user.login_name} should have {expected_history} historical records"
            )

        # Clean up
        test_user.delete()
        for user in created_users:
            user.delete()

    def test_i_active_status(self):
        always_valid = User(
            username="always_valid", i_user=InteractiveUser(login_name="always_valid")
        )
        self.assertTrue(always_valid.is_active)

        import datetime
        # user is not business history yet
        # not_yet_active = User(
        #     username="always_valid",
        #     i_user=InteractiveUser(
        #         login_name="not_yet_active",
        #         validity_from=datetime.datetime.now() + datetime.timedelta(days=1),
        #     ),
        # )
        # self.assertFalse(not_yet_active.is_active)

        not_active_anymore = User(
            username="always_valid",
            i_user=InteractiveUser(
                login_name="not_active_anymore",
                active=False,
                date_deactivated=datetime.datetime.now() + datetime.timedelta(days=-1),
            ),
        )
        self.assertFalse(not_active_anymore.is_active)


class SaveNoOpTestCase(TestCase):
    """Re-saving an existing instance with no dirty fields must be a silent no-op:
    no ValidationError, no version bump, no new history row.

    Guards both base-class save() implementations:
      - core.models.openimis_model.OpenIMISHistoryMixin.save (covered end-to-end via InteractiveUser)
      - core.models.history_model.HistoryModel.save (covered via direct MagicMock invocation,
        since core has no concrete HistoryBusinessModel subclass)
    """

    def test_openimis_model_save_is_noop_when_not_dirty(self):
        cache.clear()
        language, _ = Language.objects.get_or_create(
            code="en", defaults={"name": "English", "sort_order": 1}
        )
        user = InteractiveUser.objects.create(
            login_name="noop_save_user",
            last_name="NoOp",
            other_names="Test",
            language=language,
        )
        baseline_version = user.version
        baseline_history_count = user.history.count()

        result = user.save()

        self.assertIsNone(result)
        user.refresh_from_db()
        self.assertEqual(user.version, baseline_version)
        self.assertEqual(user.history.count(), baseline_history_count)


    def test_history_model_save_is_noop_when_not_dirty(self):
        instance = MagicMock()
        instance.id = "existing-id"
        instance.version = 7
        instance.is_dirty.return_value = False

        try:
            result = HistoryModel.save(instance)
        except ValidationError:
            self.fail("HistoryModel.save should not raise on a no-op save")

        self.assertIsNone(result)
        self.assertEqual(instance.version, 7)
        instance.is_dirty.assert_called_with(check_relationship=True)
