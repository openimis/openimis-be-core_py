from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ObjectExistsValidationMixin:
    INVALID_UPDATE_ID_MSG = _("%(model)s for id  %(id)s does not exists")

    @classmethod
    def validate_object_exists(cls, id_):
        existing = cls.OBJECT_TYPE.objects.filter(id=id_).first()
        if not existing:
            raise ValidationError(cls.INVALID_UPDATE_ID_MSG % {'id': id_, 'model': str(cls.OBJECT_TYPE)})
