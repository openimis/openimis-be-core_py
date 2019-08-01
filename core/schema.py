from django.db import connection
from django.db.models import Q
import graphene
import re
from graphene_django import DjangoObjectType
from .models import ModuleConfiguration, Control
from datetime import datetime as py_datetime


class ControlGrapQLType(DjangoObjectType):
    class Meta:
        model = Control


class ModuleConfigurationGrapQLType(DjangoObjectType):
    controls = graphene.List(ControlGrapQLType)

    def resolve_controls(parent, info):
        # TODO: find a way to prevent the N+1 query!
        return Control.objects.filter(field_name__startswith=parent.module+'.')

    class Meta:
        model = ModuleConfiguration


class Query(graphene.ObjectType):
    core_controls = graphene.List(
        ControlGrapQLType,
        module=graphene.String(required=True)
    )
    core_module_configurations = graphene.List(
        ModuleConfigurationGrapQLType,
        validity=graphene.String(),
        layer=graphene.String())

    def resolve_core_module_configurations(self, info, **kwargs):
        validity = kwargs.get('validity')
        # configuration is loaded before even the core module
        # the datetime is ALWAYS a Gregorian one
        # (whatever datetime is used in business modules)
        if validity is None:
            validity = py_datetime.now()
        else:
            d = re.split('\D', validity)
            validity = py_datetime(*[int('0'+x) for x in d][:6])
        # is_exposed indicates wherever a configuration
        # is safe to be accessible from api
        # DON'T EXPOSE (backend) configurations that contain credentials,...
        crits = (
            Q(is_disabled_until=None) | Q(is_disabled_until__lt=validity),
            Q(is_exposed=True)
        )
        layer = kwargs.get('layer')
        if layer is not None:
            crits = (*crits, Q(layer=layer))
        return ModuleConfiguration.objects.filter(*crits)

    def resolve_core_controls(self, info, **kwargs):
        return Control.objects.filter(
            field_name__startswith=kwargs.get('module')+"."
        )
