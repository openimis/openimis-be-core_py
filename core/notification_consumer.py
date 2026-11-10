from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from core.notifications import _notification_group


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Signal inbox changes; clients retrieve content through GraphQL."""

    async def connect(self):
        user = self.scope.get("user")
        if (
            not getattr(settings, "NOTIFICATION_WEBSOCKET_ENABLED", False)
            or user is None
            or not user.is_authenticated
        ):
            await self.close(code=4401)
            return

        self.notification_group = _notification_group(user.pk)
        await self.channel_layer.group_add(
            self.notification_group,
            self.channel_name,
        )
        await self.accept()

    async def disconnect(self, close_code):
        notification_group = getattr(self, "notification_group", None)
        if notification_group:
            await self.channel_layer.group_discard(
                notification_group,
                self.channel_name,
            )

    async def notification_changed(self, event):
        await self.send_json(
            {
                "type": "notification.inbox.changed",
                "version": 1,
            }
        )
