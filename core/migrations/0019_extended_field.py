from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0018_auto_20230318_1551'),
    ]

    operations = [
        migrations.RunSQL('ALTER TABLE [tblOfficer] ADD [JsonExt] TEXT'
                          if settings.MSSQL else
                          'ALTER TABLE "tblOfficer" ADD "JsonExt" jsonb'),

    ]