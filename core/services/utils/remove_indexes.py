from django.db import connection, migrations
import os


class RemoveIndexForField(migrations.RunPython):
    def __init__(self, app_name, model_name, field_name) -> None:
        self.app_name = app_name
        self.model_name = model_name
        self.field_name = field_name
        super().__init__(self.remove_index, self.reverse_remove_index)

    def remove_index(self, app, schema_editor):
        model = app.get_model(self.app_name, self.model_name)
        field = model._meta.get_field(self.field_name)

        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
            for constraint_name, constraint_info in constraints.items():
                if constraint_info["index"] and any(
                        field.column.lower() == col.lower() for col in constraint_info["columns"]):
                    if os.environ.get("DB_DEFAULT") == 'mssql':
                        cursor.execute(f"DROP INDEX {constraint_name} ON {model._meta.db_table}")
                    else:
                        cursor.execute(f'DROP INDEX "{constraint_name}"')

    def reverse_remove_index(self, app, schema_editor):
        pass
