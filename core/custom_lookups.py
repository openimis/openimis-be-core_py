import json
from django.db import NotSupportedError
from django.db.models import Lookup, Transform
from django.db.models import Field, lookups, CharField
import collections

from jsonfallback.fields import FallbackJSONField, FallbackLookup, JsonAdapter


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
        print(sql_statement)
        print(params)
        return sql_statement, params

    def _prepare_dict_value(self, json_ext):
        def flatten(dd, separator, prefix):
            return {
                prefix + separator + k if prefix else k: v
                for kk, vv in dd.items()
                for k, v in flatten(vv, separator, kk).items()
            } if isinstance(dd, dict) else {prefix: str(dd)}

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
