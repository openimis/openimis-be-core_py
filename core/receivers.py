from django.dispatch import receiver
import sys
from django.apps import apps
from django.db.models.signals import post_save, post_delete
from contextlib import suppress
from core.models.user import Officer, Role
from django.core.cache import cache
from django_redis.cache import RedisCache


@receiver([post_save, post_delete], sender=Officer)
def _post_save_eo_receiver(sender, instance, **kwargs):
    with suppress(AttributeError):
        cache.delete(f"user_eo_{instance.code}")
        cache.delete(f"rights_{instance.code}")

@receiver([post_save, post_delete], sender=Role)
def _post_save_rolerights_receiver(sender, instance, **kwargs):
    with suppress(AttributeError):
        if isinstance(cache, RedisCache):
            cache.delete("rights_*")
        else:
            cache.clear()
        
if 'claim' in sys.modules:
    ClaimAdmin = apps.get_model('claim', 'ClaimAdmin')
    @receiver([post_save, post_delete], sender=ClaimAdmin)
    def _post_save_ca_receiver(sender, instance, **kwargs):
        with suppress(AttributeError):
            cache.delete(f"user_ca_{instance.code}")
            cache.delete(f"rights_{instance.code}")
