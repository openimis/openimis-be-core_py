from django.urls import path

from core.notification_consumer import NotificationConsumer


websocket_urlpatterns = [
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
