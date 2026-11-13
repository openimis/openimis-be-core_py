from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TestCase, override_settings
from graphene import Schema
from graphene.test import Client

from core.models import Notification, Role
from core.notification_consumer import NotificationConsumer
from core.notifications import notify
from core.schema import Mutation, Query
from core.test_helpers import create_test_interactive_user, create_test_role
from core.models.openimis_graphql_test_case import BaseTestContext


class NotificationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="notification_user")
        cls.other = create_test_interactive_user(username="notification_other")
        cls.role = create_test_role(name="Notification role")
        cls.user.i_user.user_roles.create(role=Role.objects.get(id=cls.role.id))

    def context(self, user):
        return BaseTestContext(user).get_request()

    def execute(self, query, user, variables=None):
        client = Client(Schema(query=Query, mutation=Mutation))
        return client.execute(query, variables=variables, context=self.context(user))

    def test_notify_role_creates_one_retry_safe_row_per_user(self):
        for _ in range(2):
            notify(
                self.role,
                "task.assigned",
                "notification.task.title",
                "notification.task.message",
                idempotency_key="task:1:assigned",
            )
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 1)

    def test_inbox_is_private_and_mark_read_is_idempotent(self):
        notify(
            self.user,
            "task.assigned",
            "notification.task.title",
            "notification.task.message",
        )[0]
        query = "{ unreadNotificationCount notifications(first: 10) { edges { node { id uuid type readAt } } } }"
        own = self.execute(query, self.user)
        other = self.execute(query, self.other)
        self.assertEqual(own["data"]["unreadNotificationCount"], 1)
        self.assertEqual(len(own["data"]["notifications"]["edges"]), 1)
        self.assertEqual(other["data"]["unreadNotificationCount"], 0)

        mutation = "mutation($ids: [UUID]!) { markNotificationsRead(ids: $ids) { updatedCount } }"
        variables = {"ids": [own["data"]["notifications"]["edges"][0]["node"]["uuid"]]}
        first = self.execute(mutation, self.user, variables)
        second = self.execute(mutation, self.user, variables)
        self.assertEqual(first["data"]["markNotificationsRead"]["updatedCount"], 1)
        self.assertEqual(second["data"]["markNotificationsRead"]["updatedCount"], 0)

    @override_settings(NOTIFICATION_WEBSOCKET_ENABLED=True)
    @patch("channels.layers.get_channel_layer")
    def test_notify_signals_recipient_after_commit(self, get_channel_layer):
        channel_layer = AsyncMock()
        get_channel_layer.return_value = channel_layer

        with self.captureOnCommitCallbacks(execute=True):
            notify(
                self.user,
                "task.assigned",
                "notification.task.title",
                "notification.task.message",
            )

        channel_layer.group_send.assert_awaited_once_with(
            f"notification_user_{self.user.id}",
            {"type": "notification.changed"},
        )

    @override_settings(
        NOTIFICATION_WEBSOCKET_ENABLED=True,
        CHANNEL_LAYERS={
            "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
        },
    )
    def test_authenticated_socket_receives_versioned_change_event(self):
        user = self.user

        async def scenario():
            communicator = WebsocketCommunicator(
                NotificationConsumer.as_asgi(),
                "/ws/notifications/",
            )
            communicator.scope["user"] = user
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await get_channel_layer().group_send(
                f"notification_user_{user.id}",
                {"type": "notification.changed"},
            )
            self.assertEqual(
                await communicator.receive_json_from(),
                {"type": "notification.inbox.changed", "version": 1},
            )
            await communicator.disconnect()

        async_to_sync(scenario)()
