import sys
from contextlib import suppress

from django import apps
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.models.user import Officer


@receiver([post_save, post_delete], sender=Officer)
def _post_save_eo_receiver(sender, instance, **kwargs):
    with suppress(AttributeError):
        cache.delete(f"user_eo_{instance.code}")


if "claim" in sys.modules:
    ClaimAdmin = apps.get_model("claim", "ClaimAdmin")

    @receiver([post_save, post_delete], sender=ClaimAdmin)
    def _post_save_ca_receiver(sender, instance, **kwargs):
        with suppress(AttributeError):
            cache.delete(f"user_ca_{instance.code}")
