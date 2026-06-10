# Generated manually for migrating admin users to superuser

from django.db import migrations, models
from core.utils import uuidv7


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_remove_user_legacy_id_remove_user_validity_from_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalinteractiveuser",
            name="uuid",
            field=models.UUIDField(
                db_column="UUID",
                db_index=True,
                default=uuidv7,
                editable=False,
            ),
        ),
        migrations.AlterField(
            model_name="interactiveuser",
            name="uuid",
            field=models.UUIDField(
                db_column="UUID", default=uuidv7, editable=False, unique=True
            ),
        ),
    ]
