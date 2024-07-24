from functools import wraps
from django.db.models import QuerySet

from core.data_masking import MaskingClassStorage


def anonymize_gql():
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            model = kwargs.get('model', None)
            if model:
                masking_class = MaskingClassStorage.get_masking_class(model.__name__)
                if masking_class:
                    masking_enabled = masking_class.masking_enabled
                    if masking_enabled:
                        if isinstance(result, QuerySet):
                            print('ok')
                            for obj in result:
                                masking_class.apply_mask(obj)
            return result
        return wrapper
    return decorator
