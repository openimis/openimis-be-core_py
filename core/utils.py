import graphene
from django.db.models import Q
import core


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


def filter_validity(arg='validity', **kwargs):
    validity = kwargs.get(arg)
    if validity is None:
        validity = core.datetime.datetime.now()
    return (
        Q(validity_from=None) | Q(validity_from__lte=validity),
        Q(validity_to=None) | Q(validity_to__gte=validity)
    )


def prefix_filterset(prefix, filterset):
    if type(filterset) is dict:
        return {(prefix + k): v for k, v in filterset.items()}
    elif type(filterset) is list:
        return [(prefix + x) for x in filterset]
    else:
        return filterset


PATIENT_CATEGORY_MASK_MALE = 1
PATIENT_CATEGORY_MASK_FEMALE = 2
PATIENT_CATEGORY_MASK_ADULT = 4
PATIENT_CATEGORY_MASK_MINOR = 8


def patient_category_mask(insuree, target_date):
    if type(target_date) is str:
        from core import datetime
        target_date = datetime.date(*[int(x) for x in target_date.split("-")])  # TODO: this should be nicer
    mask = 0
    if insuree.gender in ('M', 'O'):
        mask = mask | PATIENT_CATEGORY_MASK_MALE
    else:
        mask = mask | PATIENT_CATEGORY_MASK_FEMALE

    if insuree.dob:
        if insuree.is_adult(target_date):
            mask = mask | PATIENT_CATEGORY_MASK_ADULT
        else:
            mask = mask | PATIENT_CATEGORY_MASK_MINOR
    else:
        raise NotImplementedError("date of birth of insuree is unknown")  # TODO What should we do in this case ?
    return mask


class ExtendedConnection(graphene.Connection):
    """
    Adds total_count and edge_count to Graphene Relay connections. To use, simply add to the
    Graphene object definition Meta:
    `connection_class = ExtendedConnection`
    """
    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(root, info, **kwargs):
        return root.length

    def resolve_edge_count(root, info, **kwargs):
        return len(root.edges)
