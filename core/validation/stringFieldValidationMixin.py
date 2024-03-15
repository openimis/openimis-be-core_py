from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class StringFieldValidationMixin:
    CODE_STRING_EMPTY_MSG = _("core.validation.stringFieldValidationMixin.empty_string")
    CODE_STRING_WHITESPACE_START_MSG = _("core.validation.stringFieldValidationMixin.string_starts_with_whitespace")
    CODE_STRING_WHITESPACE_END_MSG = _("core.validation.stringFieldValidationMixin.string_ends_with_whitespace")

    @classmethod
    def validate_empty_string(cls, string):
        if not string:
            raise ValidationError(cls.CODE_STRING_EMPTY_MSG)
        if not string.replace(" ", ""):
            raise ValidationError(cls.CODE_STRING_EMPTY_MSG)

    @classmethod
    def validate_string_whitespace_start(cls, string):
        cls.validate_empty_string(string)
        if string.startswith(" "):
            raise ValidationError(cls.CODE_STRING_WHITESPACE_START_MSG)

    @classmethod
    def validate_string_whitespace_end(cls, string):
        cls.validate_empty_string(string)
        if string.endswith(" "):
            raise ValidationError(cls.CODE_STRING_WHITESPACE_END_MSG)
