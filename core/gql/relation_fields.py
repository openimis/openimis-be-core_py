"""Foreign keys and one-to-one relations resolve as with graphene-django 2.

graphene-django 3 resolves them through the related type's ``get_queryset``
(``get_node``) and answers null when that type hides the row, which changed
what a user sees through a relation (a health facility's location, a policy's
product...) and turns a hidden row into an error on a non-null field. openIMIS
applies row security to what a user lists and looks up; whether it should also
cut relations is a functional decision, not something to change with a
dependency bump, so the graphene-django 2 converters are restored here.
"""
from django.db import models
from graphene import Dynamic, Field
from graphene_django.converter import convert_django_field, get_django_field_description


def _relation_field(field, registry=None):
    model = field.related_model

    def dynamic_type():
        _type = registry.get_type_for_model(model)
        if not _type:
            return None
        return Field(_type, description=get_django_field_description(field), required=not field.null)

    return Dynamic(dynamic_type)


def _reverse_one_to_one_field(field, registry=None):
    model = field.related_model

    def dynamic_type():
        _type = registry.get_type_for_model(model)
        if not _type:
            return None
        return Field(_type)

    return Dynamic(dynamic_type)


def register_relation_converters():
    """Called from CoreConfig.ready(), before any module builds its GraphQL types."""
    convert_django_field.register(models.ForeignKey)(_relation_field)
    convert_django_field.register(models.OneToOneField)(_relation_field)
    convert_django_field.register(models.OneToOneRel)(_reverse_one_to_one_field)
