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
from core.custom_filters import CustomFilterWizardStorage
from core.models import ExportableQueryModel
from graphql.utils.ast_to_dict import ast_to_dict


logger = logging.getLogger(__file__)


class ExportableQueryMixin:
    export_patches: Dict[str, List[Callable[[DataFrame], DataFrame]]] = {}
    module_name: str
    object_type: str
    related_field: str

    @classmethod
    def get_module_name(cls) -> str:
        if not hasattr(cls, 'module_name') or getattr(cls, 'module_name') is None:
            error_msg = (
                "The class using `ExportableQueryMixin` must specify the `module_name` property "
                "when the customFilters argument is specified. Please override the `module_name` "
                "property in the Query schema to specify how to append custom filters for the specific object."
            )
            raise NotImplementedError(error_msg)
        return cls.module_name

    @classmethod
    def get_object_type(cls) -> str:
        if not hasattr(cls, 'object_type') or getattr(cls, 'object_type') is None:
            error_msg = (
                "The class using `ExportableQueryMixin` must specify the `object_type` property "
                "when the customFilters argument is specified. Please override the `object_type` "
                "property in the Query schema to specify how to append custom filters for the specific object."
            )
            raise NotImplementedError(error_msg)
        return cls.object_type

    @classmethod
    def get_related_field(cls):
        if not hasattr(cls, 'related_field') or getattr(cls, 'related_field') is None:
            return None
        return cls.related_field

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
            custom_filters = kwargs.pop("customFilters", None)
            export_fields = [cls._adjust_notation(f) for f in kwargs.pop('fields')]
            fields_mapping = json.loads(kwargs.pop('fields_columns'))
            qs = default_resolve(None, info, **kwargs)
            qs = qs.filter(**kwargs)
            qs = cls.__append_custom_filters(custom_filters, qs)
            export_file = ExportableQueryModel\
                .create_csv_export(qs, export_fields, info.context.user, column_names=fields_mapping,
                                   patches=cls.get_patches_for_field(field_name))

            return export_file.name

        setattr(cls, new_function_name, types.MethodType(exporter, cls))

    @classmethod
    def __append_custom_filters(cls, custom_filters, queryset):
        if custom_filters:
            module_name = cls.get_module_name()
            object_type = cls.get_object_type()
            related_field = cls.get_related_field()
            queryset = CustomFilterWizardStorage.build_custom_filters_queryset(
                module_name,
                object_type,
                custom_filters,
                queryset,
                relation=related_field
            )
        return queryset
