from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):
    """
    Re-apply the widening of tblOfficer.Code and tblOfficer.VEOCode from
    varchar(8) (their original 0008 definition) to varchar(50).

    Migration 0020 already declares an AlterField for these columns, but on
    environments initialised from a legacy SQL dump with the historical
    migrations faked, the underlying ALTER COLUMN never executed. Saving an
    officer whose username is longer than 8 characters (e.g. via the frontend
    /admin/users screen when adding a role) then fails with
    "value too long for type character varying(8)". Running this SQL directly
    is a no-op when the columns are already varchar(50).
    """

    dependencies = [
        ("core", "0035_migrate_admin_users_to_superuser"),
    ]

    psql_forward = (
        'ALTER TABLE "tblOfficer" ALTER COLUMN "Code" TYPE varchar(50);'
        'ALTER TABLE "tblOfficer" ALTER COLUMN "VEOCode" TYPE varchar(50);'
    )
    mssql_forward = (
        "ALTER TABLE [tblOfficer] ALTER COLUMN [Code] NVARCHAR(50) NOT NULL;"
        "ALTER TABLE [tblOfficer] ALTER COLUMN [VEOCode] NVARCHAR(50) NULL;"
    )

    operations = [
        migrations.RunSQL(
            mssql_forward if settings.MSSQL else psql_forward,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
