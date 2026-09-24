from django.contrib.auth.models import Permission
from django.db import models


class RightPermission(models.Model):
    """The django permission matching an openIMIS right."""

    permission = models.OneToOneField(
        Permission,
        on_delete=models.CASCADE,
        related_name="openimis_right",
        help_text="The django permission, reused as is when it already exists.",
    )
    right_id = models.IntegerField(
        db_index=True,
        help_text=(
            "The openIMIS identifier the roles carry. Not unique: several actions "
            "may share one right."
        ),
    )

    class Meta:
        db_table = "core_RightPermission"
        verbose_name = "right / permission mapping"
        verbose_name_plural = "right / permission mappings"

    def __str__(self):
        return f"{self.permission} -> {self.right_id}"
