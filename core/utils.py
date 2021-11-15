import core
import graphene
from django.db.models import Q
from django.utils.translation import gettext as _

__all__ = [
    "TimeUtils",
    "full_class_name",
    "comparable",
    "filter_validity",
    "prefix_filterset",
    "assert_string_length",
    "PATIENT_CATEGORY_MASK_MALE",
    "PATIENT_CATEGORY_MASK_FEMALE",
    "PATIENT_CATEGORY_MASK_ADULT",
    "PATIENT_CATEGORY_MASK_MINOR",
    "patient_category_mask",
    "ExtendedConnection",
    "get_scheduler_method_ref",
    "ExtendedRelayConnection",
]


class TimeUtils(object):

    @classmethod
    def now(cls):
        return core.datetime.datetime.now()

    @classmethod
    def date(cls):
        return core.datetime.datetime.date(cls.now())


def full_class_name(o):
    module = o.__class__.__module__
    if module is None or module == str.__class__.__module__:
        return o.__class__.__name__
    return module + '.' + o.__class__.__name__


def comparable(cls):
    """ Class decorator providing generic comparison functionality """

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)

    cls.__eq__ = __eq__
    cls.__ne__ = __ne__
    return cls


def filter_validity(arg="validity", **kwargs):
    validity = kwargs.get(arg)
    if validity is None:
        return (
            Q(validity_from__lte=core.datetime.datetime.now()),
            Q(legacy_id__isnull=True),
        )
    return (
       Q(validity_from__lte=validity),
        Q(validity_to__isnull=True) | Q(validity_to__gte=validity),
    )


def filter_validity_business_model(arg='dateValidFrom__Gte', arg2='dateValidTo__Lte', **kwargs):
    date_valid_from = kwargs.get(arg)
    date_valid_to = kwargs.get(arg2)
    #default scenario
    if not date_valid_from and not date_valid_to:
        today = core.datetime.datetime.now()
        return __place_the_filters(date_start=today, date_end=None)

    # scenario - only date valid to set
    if not date_valid_from and date_valid_to:
        today = core.datetime.datetime.now()
        oldest = min([today, date_valid_to])
        return __place_the_filters(date_start=oldest, date_end=date_valid_to)

    # scenario - only date valid from
    if date_valid_from and not date_valid_to:
        return __place_the_filters(date_start=date_valid_from, date_end=None)

    # scenario - both filters set
    if date_valid_from and date_valid_to:
        return __place_the_filters(date_start=date_valid_from, date_end=date_valid_to)


def __place_the_filters(date_start, date_end):
    """funtion related to 'filter_validity_business_model'
    function so as to set up the chosen filters
    to filter the validity of the entity
    """
    if not date_end:
        return (
            Q(date_valid_from__isnull=False),
            Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=date_start)
        )
    return (
        Q(date_valid_from__lte=date_end),
        Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=date_start)
    )


def append_validity_filter(**kwargs):
    default_filter = kwargs.get('applyDefaultValidityFilter', False)
    date_valid_from = kwargs.get('dateValidFrom__Gte', None)
    date_valid_to = kwargs.get('dateValidTo__Lte', None)
    filters = []
    # check if we can use default filter validity
    if date_valid_from is None and date_valid_to is None:
        if default_filter:
            filters = [*filter_validity_business_model(**kwargs)]
        else:
            filters = []
    else:
        filters = [*filter_validity_business_model(**kwargs)]
    return filters


def filter_is_deleted(arg='is_deleted', **kwargs):
    is_deleted = kwargs.get(arg)
    if is_deleted is None:
        is_deleted = False
    return (
        Q(is_deleted=is_deleted)
    )


def prefix_filterset(prefix, filterset):
    if type(filterset) is dict:
        return {(prefix + k): v for k, v in filterset.items()}
    elif type(filterset) is list:
        return [(prefix + x) for x in filterset]
    else:
        return filterset


def assert_string_length(str_value, length):
    if length and len(str_value) > length:
        raise Exception(
            _("core.string.over_max_length") % {
                'value': str_value, 'max_length': length})


PATIENT_CATEGORY_MASK_MALE = 1
PATIENT_CATEGORY_MASK_FEMALE = 2
PATIENT_CATEGORY_MASK_ADULT = 4
PATIENT_CATEGORY_MASK_MINOR = 8


def patient_category_mask(insuree, target_date):
    if type(target_date) is str:
        from core import datetime
        # TODO: this should be nicer
        target_date = datetime.date(*[int(x) for x in target_date.split("-")])
    mask = 0
    if not insuree.gender:
        raise NotImplementedError(_("core.insuree.unknown_gender"))
    if not insuree.dob:
        raise NotImplementedError(_("core.insuree.unknown_dob"))

    if insuree.gender.code in ('M', 'O'):
        mask = mask | PATIENT_CATEGORY_MASK_MALE
    else:
        mask = mask | PATIENT_CATEGORY_MASK_FEMALE

    if insuree.is_adult(target_date):
        mask = mask | PATIENT_CATEGORY_MASK_ADULT
    else:
        mask = mask | PATIENT_CATEGORY_MASK_MINOR
    return mask


class ExtendedConnection(graphene.Connection):
    """
    Adds total_count and edge_count to Graphene connections. To use, simply add to the
    Graphene object definition Meta:
    `connection_class = ExtendedConnection`
    """
    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(self, info, **kwargs):
        return self.length

    def resolve_edge_count(self, info, **kwargs):
        return len(self.edges)


def get_scheduler_method_ref(name):
    """
    Use to retrieve the method reference from a str name. This is necessary when the module cannot be imported from
    that location.
    :param name: claim.module.submodule.method or similar name
    :return: reference to the method
    """
    split_name = name.split(".")
    module = __import__(".".join(split_name[:-1]))
    for subitem in split_name[1:]:
        module = getattr(module, subitem)
    return module


class ExtendedRelayConnection(graphene.relay.Connection):
    """
    Adds total_count and edge_count to Graphene Relay connections.
    """
    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(self, info, **kwargs):
        return len(self.iterable)

    def resolve_edge_count(self, info, **kwargs):
        return len(self.edges)


def get_first_or_default_language():
    from core.models import Language
    sorted_languages = Language.objects.filter(sort_order__isnull=False)
    if sorted_languages.exists():
        return sorted_languages.order_by('sort_order').first()
    else:
        return Language.objects.first()
