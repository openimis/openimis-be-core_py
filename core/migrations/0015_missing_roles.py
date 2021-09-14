import logging
from functools import lru_cache

from django.db import migrations
from core.models import RoleRight, Role

logger = logging.getLogger(__name__)

ROLE_RIGHTS_ID = [101201, 101101, 101001, 101105]
MANAGER_ROLE_IS_SYSTEM = 256  # By default missing rights are assigned to ClaimAdmin role


@lru_cache(maxsize=1)
def __get_role_owner() -> Role:
    return Role.objects.get(is_system=256, validity_to=None)


def __role_already_exists(right_id):
    sc = RoleRight.objects.filter(role__uuid=__get_role_owner().uuid, right_id=right_id)
    return sc.count() > 0


def create_role_right(apps, schema_editor):
    if schema_editor.connection.alias != 'default':
        return
    for right_id in ROLE_RIGHTS_ID:
        if __role_already_exists(right_id):
            logger.warning(F"Role right {right_id} already assigned for role {__get_role_owner().name}, skipping")
            return
        role_owner = Role.objects.get(is_system=256, validity_to=None)
        new_role = RoleRight(
            role=role_owner,
            right_id=right_id,
            audit_user_id=None,
        )
        new_role.save()

    # Your migration code goes here


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_users')
    ]

    operations = [
        migrations.RunPython(create_role_right),
    ]
