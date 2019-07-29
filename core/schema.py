from django.db.models import Q
import graphene
import re
from graphene_django import DjangoObjectType
from .models import ModuleConfiguration
from datetime import datetime as py_datetime


class ModuleConfigurationType(DjangoObjectType):
    class Meta:
        model = ModuleConfiguration


class Query(graphene.ObjectType):
    # DON'T EXPOSE BACKEND MODULE CONFIGURATIONS
    # (may contain credentials,...)!
    module_configurations = graphene.List(
        ModuleConfigurationType,
        validity=graphene.String(),
        layer=graphene.String())

    def resolve_module_configurations(self, info, **kwargs):
        validity = kwargs.get('validity')
        # configuration is loaded before even the core module
        # the datetime is ALWAYS a Gregorian one
        # (whatever datetime is used in business modules)
        if validity is None:
            validity = py_datetime.now()
        else:
            d = re.split('\D', validity)
            validity = py_datetime(*[int('0'+x) for x in d][:6])
        crits = (
            Q(is_disabled_until=None) | Q(is_disabled_until__lt=validity),
            Q(is_exposed=True)
        )
        layer = kwargs.get('layer')
        if layer is not None:
            crits = (*crits, Q(layer=layer))

        return ModuleConfiguration.objects.filter(*crits)
