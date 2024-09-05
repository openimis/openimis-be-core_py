import logging
from functools import lru_cache
from core.utils import insert_role_right_for_system
from django.db import migrations, models

logger = logging.getLogger(__name__)

ROLE_RIGHTS_ID = [101201, 101101, 101001, 101105]
MANAGER_ROLE_IS_SYSTEM = 64  # By default missing rights are assigned to ClaimAdmin role



def create_role_right(apps, schema_editor):
    RoleRight = apps.get_model('core', 'RoleRight')
    Role = apps.get_model('core', 'Role')
    for right_id in ROLE_RIGHTS_ID:
        insert_role_right_for_system(256, right_id, apps )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_users')
    ]

    operations = [
        migrations.AddField(
            model_name='roleright',
            name='role',
            field=models.ForeignKey(db_column='RoleID', on_delete=models.deletion.DO_NOTHING, related_name='rights', to='core.role'),
        ),
        migrations.RunPython(create_role_right),
    ]
