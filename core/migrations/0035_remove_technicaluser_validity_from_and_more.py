# Generated manually
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_remove_user_legacy_id_remove_user_validity_from_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='technicaluser',
            name='validity_from',
        ),
        migrations.RemoveField(
            model_name='technicaluser',
            name='validity_to',
        ),
        migrations.RemoveField(
            model_name='interactiveuser',
            name='validity_from',
        ),
        migrations.RemoveField(
            model_name='interactiveuser',
            name='validity_to',
        ),
        migrations.RemoveField(
            model_name='historicalinteractiveuser',
            name='validity_from',
        ),
        migrations.RemoveField(
            model_name='historicalinteractiveuser',
            name='validity_to',
        ),
    ]
