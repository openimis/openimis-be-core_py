from django.db.models import Lookup

from jsonfallback.fields import FallbackJSONField


@FallbackJSONField.register_lookup
class JsonContains(Lookup):
    lookup_name = 'jsoncontains'

    sql_server_json_key_prefix = '$'
    sql_server_nested_json_separator = '.'
    BASE_SQL = '(JSON_VALUE(cast({} as nvarchar(max)), %s)=%s)'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)

        rhs_params[0].prepare(connection)
        params = self._build_sql_params(lhs, rhs_params[0].adapted)
        sql_statement = ' AND '.join([self.BASE_SQL.format(lhs) for _ in range(0, len(rhs_params[0].adapted))])
        return sql_statement, params

    def _prepare_dict_value(self, json_ext):
        def flatten(dictionary, separator, prefix):
            return {
                prefix + separator + key if prefix else key: value
                for nested_key, nested_value in dictionary.items()
                for key, value in flatten(nested_value, separator, nested_key).items()
            } if isinstance(dictionary, dict) else {prefix: str(dictionary)}

        base_prefix = self.sql_server_json_key_prefix
        base_separator = self.sql_server_nested_json_separator
        return flatten(json_ext, base_separator, base_prefix)

    def _build_sql_params(self, entity, json_conditions, ):
        adjusted_conditions = self._prepare_dict_value(json_conditions)
        conditions = []
        for json_key, expected_value in adjusted_conditions.items():
            # conditions.append(entity)
            conditions.append(json_key)
            conditions.append(expected_value)
        return conditions
