# Generated by Django 4.2.9 on 2024-02-07 16:47

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_mutationlog_autogenerated_code'),
    ]

    operations = [
        migrations.AlterField(
            model_name='interactiveuser',
            name='last_login',
            field=models.DateTimeField(blank=True, db_column='LastLogin', null=True),
        ),
        migrations.AlterField(
            model_name='technicaluser',
            name='validity_from',
            field=models.DateTimeField(blank=True, default=datetime.datetime.now, null=True),
        ),
    ]
