import logging

from django.db import migrations

logger = logging.getLogger(__name__)


MIGRATION_SQL = """
    IF NOT EXISTS (SELECT * FROM imis.dbo.tblLanguages WHERE LanguageCode = 'en-gm')
    BEGIN
        INSERT INTO imis.dbo.tblLanguages
        (LanguageCode, LanguageName, SortOrder)
        VALUES('en-gm', 'Gambian English ', 3);
    END
"""


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_add_last_login_on_interactive_user')
    ]

    operations = [
        migrations.RunSQL(MIGRATION_SQL)
    ]
