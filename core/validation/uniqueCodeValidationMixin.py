from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class UniqueCodeValidationMixin:
    CODE_DUPLICATE_MSG = _("Object code %(code)s is not unique.")

    @classmethod
    def validate_unique_code_name(cls, code, excluded_id=None, code_key='code'):
        if not cls._unique_code_name(code, excluded_id, code_key=code_key):
            raise ValidationError(cls.CODE_DUPLICATE_MSG % {'code': code})

    @classmethod
    def _unique_code_name(cls, code, excluded_id=None, code_key='code'):
        query = cls.OBJECT_TYPE.objects.filter(**{code_key: code})
        if excluded_id:
            query = query.exclude(id=excluded_id)

        return not query.exists()
