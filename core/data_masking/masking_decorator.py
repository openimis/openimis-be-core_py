import base64

from functools import wraps
from django.db.models import QuerySet

from core.data_masking import MaskingClassStorage


def anonymize_gql():
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            queryset = result.iterable
            model = queryset.model
            edges = result.edges
            if model:
                masking_class = MaskingClassStorage.get_masking_class(model.__name__)
                if masking_class:
                    masking_enabled = masking_class.masking_enabled
                    if masking_enabled:
                        for edge in edges:
                            masking_class.apply_mask(edge.node)
            return result
        return wrapper
    return decorator
