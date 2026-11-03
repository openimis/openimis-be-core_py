from collections.abc import Iterable

from django.db import transaction

from core.models import Notification, Role, User


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
    return created
