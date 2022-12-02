import datetime
import json
import logging
import types
import uuid
from typing import Dict, List, Callable

import graphene
import pandas as pd
from django.db import models
from graphene.types.generic import GenericScalar
from pandas import DataFrame

from core import fields
from core.models import ExportableQueryModel
from graphql.utils.ast_to_dict import ast_to_dict

logger = logging.getLogger(__file__)


class ExportableQueryMixin:
    export_patches: Dict[str, List[Callable[[DataFrame], DataFrame]]] = {}

    @classmethod
    def get_exportable_fields(cls):
        if not hasattr(cls, 'exportable_fields'):
            raise NotImplementedError(
                "Class using `ExportableQueryMixin` has to provide either exportable_fields "
                "or overwrite`get_exportable_fields` to provide list of fields that can be exported.")
        return cls.exportable_fields

    @classmethod
    def get_patches_for_field(cls, field_type):
        if field_type not in cls.get_exportable_fields():
            raise AttributeError(f"Field {field_type} is not being exported.")
        return cls.export_patches.get(field_type)

    @classmethod
    def __init_subclass_with_meta__(cls, **meta_options):
        cls._setup_exportable_fields(**meta_options)
        return super(ExportableQueryMixin, cls).__init_subclass_with_meta__(**meta_options)

    @classmethod
    def _setup_exportable_fields(cls, **meta_options):
        for field in cls.get_exportable_fields():
            field_name = F"{field}_export"
            fld = getattr(cls, field)
            new_args = fld.args
            new_args['fields'] = graphene.List(of_type=graphene.String)
            new_args['fields_columns'] = GenericScalar()
            setattr(cls, field_name, graphene.Field(graphene.String, args=new_args))
            cls.create_export_function(field)

    @classmethod
    def _adjust_notation(cls, field):
        from graphene.utils.str_converters import to_snake_case, to_camel_case
        return to_snake_case(field.replace('.', '__'))

    @classmethod
    def create_export_function(cls, field_name):
        new_function_name = f"resolve_{field_name}_export"
        default_resolve = getattr(cls, F"resolve_{field_name}", None)

        if not default_resolve:
            raise AttributeError(
                f"Query {cls} doesn't provide resolve function for {field_name}. "
                f"CSV export cannot be created")

        def exporter(cls, self, info, **kwargs):
            export_fields = [cls._adjust_notation(f) for f in kwargs['fields']]
            fields_mapping = json.loads(kwargs['fields_columns'])
            column_names = [fields_mapping.get(column) or column for column in kwargs['fields']]
            qs = default_resolve(None, info, **kwargs)

            export_file = ExportableQueryModel\
                .create_csv_export(qs, export_fields, info.context.user, column_names=column_names,
                                   patches=cls.get_patches_for_field(field_name))

            return export_file.name

        setattr(cls, new_function_name, types.MethodType(exporter, cls))



