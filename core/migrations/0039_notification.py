import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0038_rightpermission")]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("type", models.CharField(max_length=100)),
                ("severity", models.CharField(choices=[("INFO", "Info"), ("SUCCESS", "Success"), ("WARNING", "Warning"), ("ERROR", "Error")], default="INFO", max_length=10)),
                ("title_key", models.CharField(max_length=255)),
                ("message_key", models.CharField(max_length=255)),
                ("message_params", models.JSONField(blank=True, default=dict)),
                ("entity_type", models.CharField(blank=True, max_length=255, null=True)),
                ("entity_id", models.CharField(blank=True, max_length=255, null=True)),
                ("idempotency_key", models.CharField(blank=True, max_length=255, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="core.user")),
            ],
            options={"ordering": ("created_at", "id")},
        ),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["recipient", "read_at"], name="core_notif_recipient_read")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["recipient", "created_at"], name="core_notif_recipient_created")),
        migrations.AddConstraint(model_name="notification", constraint=models.UniqueConstraint(condition=models.Q(("idempotency_key__isnull", False)), fields=("recipient", "idempotency_key"), name="core_notification_recipient_idempotency")),
    ]
