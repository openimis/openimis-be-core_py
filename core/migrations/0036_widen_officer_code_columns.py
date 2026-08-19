from django.db import connection, migrations


PG_COLUMNS_EO = [("Code", "varchar(50)"), ("VEOCode", "varchar(50)")]
MSSQL_COLUMNS_EO = [("Code", "NVARCHAR(50) NOT NULL"), ("VEOCode", "NVARCHAR(50) NULL")]


PG_COLUMNS_CA = [("ClaimAdminCode", "varchar(50)")]
MSSQL_COLUMNS_CA = [("ClaimAdminCode", "NVARCHAR(50) NOT NULL")]


def widen_officer_code_columns(apps, schema_editor):
    if connection.vendor == "postgresql":
        _widen_postgresql(table_name='tblOfficer', colums=PG_COLUMNS_EO)
    elif connection.vendor == "microsoft":
        _widen_mssql(table_name='tblOfficer', colums=MSSQL_COLUMNS_EO)


def widen_claim_admin_code_columns(apps, schema_editor):
    if connection.vendor == "postgresql":
        _widen_postgresql(table_name='tblClaimAdmin', colums=PG_COLUMNS_CA)
    elif connection.vendor == "microsoft":
        _widen_mssql(table_name='tblClaimAdmin', colums=MSSQL_COLUMNS_CA)


def _pg_column_length(cursor, column_name, table_name):
    cursor.execute(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s "
        "AND column_name = %s",
        [table_name, column_name],
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _pg_dependent_views(cursor, column_names, table_name):
    cursor.execute(
        """
        SELECT DISTINCT ns.nspname, v.relname
        FROM pg_depend d
        JOIN pg_rewrite r ON r.oid = d.objid
        JOIN pg_class v ON v.oid = r.ev_class AND v.relkind = 'v'
        JOIN pg_namespace ns ON ns.oid = v.relnamespace
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_attribute a
          ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
        WHERE t.relname = %s AND a.attname = ANY(%s)
        """,
        [table_name, list(column_names)],
    )
    return [(schema, name) for schema, name in cursor.fetchall()]


def _widen_postgresql(table_name, colums):
    with connection.cursor() as cursor:
        to_widen = [
            (col, new_type)
            for col, new_type in colums
            if (_pg_column_length(cursor, col, table_name) or 0) < 50
        ]
        if not to_widen:
            return

        col_names = [col for col, _ in to_widen]
        dependent_views = _pg_dependent_views(cursor, col_names, table_name)

        view_defs = []
        for schema, name in dependent_views:
            cursor.execute(
                "SELECT definition FROM pg_views "
                "WHERE schemaname = %s AND viewname = %s",
                [schema, name],
            )
            row = cursor.fetchone()
            if row:
                view_defs.append((schema, name, row[0]))

        for schema, name, _ in view_defs:
            cursor.execute(f'DROP VIEW IF EXISTS "{schema}"."{name}" CASCADE')

        for col, new_type in to_widen:
            cursor.execute(
                f'ALTER TABLE "{table_name}" ALTER COLUMN "{col}" TYPE {new_type}'
            )

        _recreate_postgresql_views(cursor, view_defs)


def _recreate_postgresql_views(cursor, view_defs):
    pending = [
        (schema, name, f'CREATE OR REPLACE VIEW "{schema}"."{name}" AS {definition}')
        for schema, name, definition in view_defs
    ]
    while pending:
        progress = False
        remaining = []
        for schema, name, ddl in pending:
            cursor.execute("SAVEPOINT recreate_view")
            try:
                cursor.execute(ddl)
                cursor.execute("RELEASE SAVEPOINT recreate_view")
                progress = True
            except Exception:
                cursor.execute("ROLLBACK TO SAVEPOINT recreate_view")
                cursor.execute("RELEASE SAVEPOINT recreate_view")
                remaining.append((schema, name, ddl))
        if not progress:
            cursor.execute(remaining[0][2])
        pending = remaining


def _widen_mssql(table_name, colums):
    with connection.cursor() as cursor:
        for col, new_type in colums:
            cursor.execute(
                "SELECT CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = '%s' AND COLUMN_NAME = %s",
                [table_name, col],
            )
            row = cursor.fetchone()
            current = row[0] if row else None
            if current is None or current >= 50:
                continue
            cursor.execute(
                f"ALTER TABLE [{table_name}] ALTER COLUMN [{col}] {new_type};"
            )


class Migration(migrations.Migration):
    """
    Re-apply the widening of tblOfficer.Code and tblOfficer.VEOCode from
    varchar(8) (their original 0008 definition) to varchar(50).

    Migration 0020 already declares an AlterField for these columns, but on
    environments initialised from a legacy SQL dump with historical migrations
    faked, the underlying ALTER COLUMN never executed. Saving an officer whose
    username is longer than 8 characters (e.g. via /admin/users when adding a
    role) then fails with "value too long for type character varying(8)".

    The operation is a no-op when the columns are already at least 50
    characters wide, so it is safe to run on freshly-migrated databases.
    """

    dependencies = [
        ("core", "0035_migrate_admin_users_to_superuser"),
    ]

    operations = [
        migrations.RunPython(
            widen_officer_code_columns,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            widen_claim_admin_code_columns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
