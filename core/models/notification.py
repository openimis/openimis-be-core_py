import uuid

from django.db import models


class Notification(models.Model):
    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        SUCCESS = "SUCCESS", "Success"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=100)
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.INFO
    )
    title_key = models.CharField(max_length=255)
    message_key = models.CharField(max_length=255)
    message_params = models.JSONField(default=dict, blank=True)
    entity_type = models.CharField(max_length=255, blank=True, null=True)
    entity_id = models.CharField(max_length=255, blank=True, null=True)
    idempotency_key = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "idempotency_key"),
                condition=models.Q(idempotency_key__isnull=False),
                name="core_notification_recipient_idempotency",
            )
        ]
        indexes = [
            models.Index(
                fields=("recipient", "read_at"),
                name="core_notif_recipient_read",
            ),
            models.Index(
                fields=("recipient", "created_at"),
                name="core_notif_recipient_created",
            ),
        ]
