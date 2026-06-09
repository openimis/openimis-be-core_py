from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from .openimis_model import OpenIMISBusinessModel


class UserBusinessAccess(OpenIMISBusinessModel):
    user = models.ForeignKey(
        'core.User',
        on_delete=models.CASCADE,
        related_name='business_accesses'
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    object_id = models.CharField(
        max_length=36,
        null=True,
        blank=True
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    link_type = models.CharField(
        max_length=36,
        null=False,
        blank=True
    )
    class Meta:
        verbose_name = "User Business Access"
        verbose_name_plural = "User Business Accesses"
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'content_type', 'object_id']),
            models.Index(fields=['user', 'link_type']),
            models.Index(fields=['link_type', 'object_id']),
        ]