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
    else:
        d = re.split('\D', validity)
        validity = core.datetime.datetime(*[int('0'+x) for x in d][:6])
    return (
        Q(validity_from=None) | Q(validity_from__lte=validity),
        Q(validity_to=None) | Q(validity_to__gte=validity)
    )
