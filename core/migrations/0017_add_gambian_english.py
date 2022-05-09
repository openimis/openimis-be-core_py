import logging

from django.db import migrations

logger = logging.getLogger(__name__)


MIGRATION_SQL = """
    INSERT INTO imis.dbo.tblLanguages
    (LanguageCode, LanguageName, SortOrder)
    VALUES('en-gm', 'Gambian English ', 3);
"""


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_add_last_login_on_interactive_user')
    ]

    operations = [
        migrations.RunSQL(MIGRATION_SQL)
    ]
