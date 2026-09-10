from django.dispatch import receiver
import sys
from django.apps import apps
from django.db.models.signals import post_save, post_delete
from contextlib import suppress
from core.models.user import Officer, Role, RoleRight, UserRole
from core.cache_control import (
    invalidate_claim_admin,
    invalidate_officer,
    invalidate_role_rights,
    invalidate_user_rights,
)

# These receivers are triggers only: a role level change invalidates data cached
# against *other* models (the rights of every user holding the role), which no
# model level save hook can express. The keys, and the tolerance for a cache
# backend that is down, belong to core.cache_control.


@receiver([post_save, post_delete], sender=Officer)
def _post_save_eo_receiver(sender, instance, **kwargs):
    with suppress(AttributeError):
        invalidate_officer(instance.code)


@receiver([post_save, post_delete], sender=Role)
@receiver([post_save, post_delete], sender=RoleRight)
def _post_save_rolerights_receiver(sender, instance, **kwargs):
    # RoleRight points at the role it belongs to, Role is the role itself
    role_id = instance.role_id if isinstance(instance, RoleRight) else instance.pk
    invalidate_role_rights(role_id)


@receiver([post_save, post_delete], sender=UserRole)
def _post_save_userrole_receiver(sender, instance, **kwargs):
    invalidate_user_rights(instance.user_id)


if "claim" in sys.modules:
    ClaimAdmin = apps.get_model("core", "ClaimAdmin")

    @receiver([post_save, post_delete], sender=ClaimAdmin)
    def _post_save_ca_receiver(sender, instance, **kwargs):
        with suppress(AttributeError):
            invalidate_claim_admin(instance.code)
