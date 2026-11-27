from django.test import TestCase
from graphql.pyutils import is_awaitable

from core.models import User
from core.test_helpers import create_test_interactive_user


class UserAwaitableProbeTest(TestCase):
    # graphql-core 3 asks every resolved value whether it is awaitable, which looks
    # up __await__ on it. User.__getattr__ proxied that lookup to the linked user,
    # and on a row loaded with deferred fields the lookup recursed until Python gave
    # up ("maximum recursion depth exceeded" on any field returning a User).

    def test_a_user_with_deferred_fields_is_not_awaitable(self):
        user = create_test_interactive_user(username="probeAwaitable")
        deferred = User.objects.only("id").get(id=user.id)
        self.assertFalse(is_awaitable(deferred))

    def test_dunder_lookups_are_not_proxied(self):
        user = create_test_interactive_user(username="probeDunder")
        self.assertFalse(hasattr(User.objects.get(id=user.id), "__await__"))
