# Generated by Django 3.2.17 on 2023-02-20 13:01
import logging
from functools import lru_cache

from django.db import migrations
from core.models import RoleRight, Role

ROLE_RIGHT_ID = 121906
IMIS_ADMINISTRATOR_ROLE_IS_SYSTEM = 64
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def __get_role_owner() -> Role:
    return Role.objects.get(
        is_system=IMIS_ADMINISTRATOR_ROLE_IS_SYSTEM,
        validity_to=None
    )


def __role_already_exists(right_id):
    sc = RoleRight.objects.filter(role__uuid=__get_role_owner().uuid, right_id=right_id)
    return sc.count() > 0


def create_role_right(apps, schema_editor):
    if schema_editor.connection.alias != 'default':
        return
    if __role_already_exists(ROLE_RIGHT_ID):
        logger.warning(F"Role right {ROLE_RIGHT_ID} already assigned for role {__get_role_owner().name}, skipping")
        return
    role_owner = Role.objects.get(is_system=64, validity_to=None)
    new_role = RoleRight(
        role=role_owner,
        right_id=ROLE_RIGHT_ID,
        audit_user_id=None,
    )
    new_role.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_exportablequerymodel'),
    ]

    operations = [
        migrations.RunPython(create_role_right),
    ]
