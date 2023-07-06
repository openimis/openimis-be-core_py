import re
from io import StringIO

from django.core.management import call_command
from django.db import models, transaction, connection
from django.db.models import F
from django.db.models.functions import Replace
from simple_history.utils import get_history_model_for_model

from pathlib import Path
import os

from core.models import HistoryModel


class temporary_module_migration(object):
    def __init__(self, module_name):
        self.module_name = module_name
        self._check_if_module_is_local()

    def __enter__(self):
        self.migration_name = self.__create_migration()
        return self.migration_name

    def __exit__(self, exception_type, exception_value, traceback):
        """
        Delete migration file from relative path.
        """

        migrations_path = self._get_migrations_path()
        file = os.path.join(migrations_path, F'{self.migration_name}.py')
        os.remove(file)

        if exception_type:
            raise exception_type(exception_value)

    def __create_migration(self):
        out = StringIO()
        call_command('makemigrations', self.module_name, stdout=out)
        out = out.getvalue()
        x = re.compile("\/migrations\/(.*)\.py")
        migration_name = x.search(out).groups()[0]
        return migration_name

    def _check_if_module_is_local(self):
        migrations_path = self._get_migrations_path()
        if not os.path.isdir(migrations_path):
            raise ValueError(
                "Temporary migration can be created only for modules installed locally next to openimis-be_py."
                "Core module also has to be installed locally. "
                f"Either module {self.module_name} is not installed locally or it doesn't provide /migrations/ folder."
            )

    def _get_migrations_path(self):
        path_dir = Path(__file__).parent.parent.parent.parent
        relative_path = F'openimis-be-{self.module_name}_py/{self.module_name}/migrations/'
        return os.path.join(path_dir, relative_path)


class CreateTempTable:
    def __init__(self, module, model, type_of_history_model):
        self.module = module
        self.model = model
        self.type_of_history_model = type_of_history_model
        if self.type_of_history_model not in ['HISTORY_MODEL', 'BUSINESS_HISTORY_MODEL']:
            raise AttributeError("Invalid new model field type")

        versioned_model_fields = self._get_versioned_model_fields()
        self.HistoryTransitionModel = type('HistoryTransitionModel', (HistoryModel,), {
            **versioned_model_fields,
            '__module__': self.module,
        })

    @transaction.atomic
    def migrate_to_history_model(self):
        sql_queries = self._create_transition_queries()
        self.execute_sqls(sql_queries)
        print("--______________________________________________")
        print("--______________________________________________")
        print(rf"{sql_queries}")
        print("--______________________________________________")
        print("--______________________________________________")
        raise ValueError("Rollback")

    def _create_transition_queries(self):
        create_table_sql = self.migrate()
        current, historical = self.split_historical_data()
        insert_sql = self.load_current(current)
        insert_history_sql = self.load_historical(historical)
        return [
            create_table_sql,
            insert_sql,
            insert_history_sql
        ]

    def _get_versioned_model_fields(self):
        new_fields = {}
        # Add existing model fields
        data_fields = [x for x in self.model._meta.get_fields() if isinstance(x, models.fields.Field)]
        for f in data_fields:
            name = F"versioned_{f.name}"
            if name == 'versioned_id':
                # PK is replaced not transitioned
                continue

            f = f.clone()
            f.name = name
            f.db_column = name
            f.is_relation = False
            new_fields[name] = f
        return new_fields

    def migrate(self):
        with temporary_module_migration(self.module) as migration_name:
            out = StringIO()
            call_command('sqlmigrate', self.module, migration_name, stdout=out)
            out = out.getvalue()
            x = re.compile("(CREATE TABLE .*\;)")
            sql_create_table = x.findall(out)
            query = '\n;'.join(sql_create_table)
            return query, []

    def split_historical_data(self):
        historical = self.model.objects.filter(validity_to__isnull=False, legacy_id__isnull=False).all()
        current = self.model.objects.filter(legacy_id__isnull=True).all()
        return self.wrap_current(current), self.annotate_historical_fields(self.wrap_current(historical))

    def execute_sqls(self, sqls):
        with connection.cursor() as cursor:
            for sql, params in sqls:
                cursor.execute(sql, params)
            cursor.execute("SELECT COUNT(*) FROM insuree_historytransitionmodel")
            row = cursor.fetchone()
            return row

    def get_history_models_annotation(self):
        versioned_model_fields = self._get_versioned_model_fields()
        extra = {
            'UserUpdatedUUID': Replace('versioned_uuid', models.Value('-'), models.Value('')),  # For now fixed
            'UUID': Replace('versioned_uuid', models.Value('-'), models.Value('')),
            'UserCreatedUUID': Replace('versioned_uuid', models.Value('-'), models.Value('')),
            'DateCreated': F('versioned_validity_from'),
            'version': models.Value(0),
            'Json_ext': F('versioned_json_ext'),
            'DateUpdated': F('versioned_validity_from'),
            'isDeleted': models.Value(False)
        }
        return [*list(versioned_model_fields.keys()), *list(extra.keys())]

    def get_historical_models_annotation(self):
        history = self.get_history_models_annotation()
        extra = {
            'history_date': F('validity_to'),
            'history_change_reason': models.Value('Versioned model migration'),
            'history_type': models.Value('+'),
            'history_user_id': Replace('versioned_uuid', models.Value('-'), models.Value('')),
        }
        return [*history, *list(extra.keys())]

    def annotate_values(self, queryset):
        versioned_model_fields = self._get_versioned_model_fields()
        aliases = {x.replace('versioned_', ''): x for x in versioned_model_fields.keys()}
        return queryset \
            .annotate(**{transition_name: F(versioned_name) for versioned_name, transition_name in aliases.items()}) \
            .all()

    def annotate_history_model_fields(self, base):
        extra = {
            'UserUpdatedUUID': Replace('versioned_uuid', models.Value('-'), models.Value('')),  # For now fixed
            'UUID': Replace('versioned_uuid', models.Value('-'), models.Value('')),
            'UserCreatedUUID': Replace('versioned_uuid', models.Value('-'), models.Value('')),
            'DateCreated': F('versioned_validity_from'),
            'version': models.Value(0),
            'Json_ext': F('versioned_json_ext'),
            'DateUpdated': F('versioned_validity_from'),
            'isDeleted': models.Case(models.When(validity_to__isnull=True, then=models.Value(False)), default=True)
        }
        base = base.annotate(**extra)
        return base

    def annotate_historical_fields(self, base):
        extra = {
            'history_date': F('validity_to'),
            'history_change_reason': models.Value('Versioned model migration'),
            'history_type': models.Value('+'),
            'history_user_id': Replace('versioned_uuid', models.Value('-'), models.Value('')),
        }
        base = base.annotate(**extra)
        return base

    def wrap_current(self, queryset):
        base = self.annotate_values(queryset)
        base = self.annotate_history_model_fields(base)
        values = self.get_history_models_annotation()
        return base.values(*values)

    def load_current(self, data):
        new_query, params = data.query.sql_with_params()
        columns = self.get_history_models_annotation()
        return F'INSERT INTO {self.HistoryTransitionModel._meta.db_table}({", ".join(columns)}) {new_query}', params

    def load_historical(self, data):
        history_table = get_history_model_for_model(self.HistoryTransitionModel)
        new_query, params = data.query.sql_with_params()
        columns = self.get_historical_models_annotation()
        return F'INSERT INTO {history_table._meta.db_table}({", ".join(columns)}) {new_query}', params
