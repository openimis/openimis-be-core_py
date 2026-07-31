from django.dispatch import receiver
import sys
from django.apps import apps
from django.db.models.signals import post_save, post_delete
from contextlib import suppress
from core.models.user import Officer, Role, RoleRight, UserRole
from django.core.cache import cache


def _clear_all_rights_cache():
    # rights are cached per user id, so a role-level change cannot target a single key
    delete_pattern = getattr(cache, "delete_pattern", None)
    if delete_pattern:
        delete_pattern("rights_*")
    else:
        cache.clear()


@receiver([post_save, post_delete], sender=Officer)
def _post_save_eo_receiver(sender, instance, **kwargs):
    with suppress(AttributeError):
        cache.delete(f"user_eo_{instance.code}")


@receiver([post_save, post_delete], sender=Role)
@receiver([post_save, post_delete], sender=RoleRight)
def _post_save_rolerights_receiver(sender, instance, **kwargs):
    _clear_all_rights_cache()


@receiver([post_save, post_delete], sender=UserRole)
def _post_save_userrole_receiver(sender, instance, **kwargs):
    cache.delete(f"rights_{instance.user_id}")
    cache.delete(f"is_admin_{instance.user_id}")


if "claim" in sys.modules:
    ClaimAdmin = apps.get_model("core", "ClaimAdmin")

    @receiver([post_save, post_delete], sender=ClaimAdmin)
    def _post_save_ca_receiver(sender, instance, **kwargs):
        with suppress(AttributeError):
            cache.delete(f"user_ca_{instance.code}")
