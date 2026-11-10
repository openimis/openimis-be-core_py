from collections.abc import Iterable
import logging

from django.conf import settings
from django.db import transaction

from core.models import Notification, Role, User


logger = logging.getLogger(__name__)


def _notification_group(user_id):
    return f"notification_user_{user_id}"


def _push_inbox_changed(notifications):
    """Hint connected clients to pull their durable inbox again."""
    if not notifications or not getattr(
        settings, "NOTIFICATION_WEBSOCKET_ENABLED", False
    ):
        return

    recipient_ids = {notification.recipient_id for notification in notifications}

    def send_after_commit():
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            channel_layer = get_channel_layer()
            if channel_layer is None:
                return
            for recipient_id in recipient_ids:
                async_to_sync(channel_layer.group_send)(
                    _notification_group(recipient_id),
                    {"type": "notification.changed"},
                )
        except Exception:
            # Push is an optional acceleration. A broker outage must never roll
            # back the stored inbox row that polling can still retrieve.
            logger.exception("Unable to signal a notification inbox change")

    transaction.on_commit(send_after_commit)


def _recipient_users(recipients):
    if isinstance(recipients, (User, Role)):
        recipients = [recipients]
    elif not isinstance(recipients, Iterable):
        recipients = [recipients]

    user_ids = set()
    role_ids = set()
    for recipient in recipients:
        if isinstance(recipient, User):
            user_ids.add(recipient.id)
        elif isinstance(recipient, Role):
            role_ids.add(recipient.id)
        else:
            user_ids.add(recipient)

    if role_ids:
        user_ids.update(
            User.objects.filter(
                i_user__user_roles__role_id__in=role_ids,
                i_user__user_roles__validity_to__isnull=True,
            ).values_list("id", flat=True)
        )
    return User.objects.filter(id__in=user_ids)


@transaction.atomic
def notify(
    recipients,
    notification_type,
    title_key,
    message_key,
    message_params=None,
    severity=Notification.Severity.INFO,
    entity_type=None,
    entity_id=None,
    idempotency_key=None,
    expires_at=None,
):
    """Store one durable notification per recipient and safely tolerate retries."""
    created = []
    for recipient in _recipient_users(recipients):
        values = {
            "type": notification_type,
            "title_key": title_key,
            "message_key": message_key,
            "message_params": message_params or {},
            "severity": severity,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "expires_at": expires_at,
        }
        if idempotency_key:
            notification, was_created = Notification.objects.get_or_create(
                recipient=recipient,
                idempotency_key=idempotency_key,
                defaults=values,
            )
            if was_created:
                created.append(notification)
        else:
            created.append(Notification.objects.create(recipient=recipient, **values))
    _push_inbox_changed(created)
    return created
