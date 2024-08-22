import functools
from inspect import getfullargspec


class ObligatoryFieldValidationError(Exception):
    ...


class ObligatoryFieldValidation:
    def __init__(self, obligatory_fields_list):
        self.obligatory_field_list = obligatory_fields_list

    def validate_obligatory_fields(self, payload):
        """
        Validate payload against obligatory field definitions. Payload have to share same fields as model in which
        data is validated. Validation is done using obligatory_fields_list. If field from obligatory field list is
        not provided as key in payload or is blank then ObligatoryFieldValidationError exception will be raised.

        :param payload: dictionary from which object will be created.
        :return: None
        """
        for field_name, control in self.obligatory_field_list.items():
            if control not in ('O', 'H', 'M'):
                raise ObligatoryFieldValidationError(
                    F'Invalid configuration for field {field_name}, value {control}'
                    F'is not proper value. Allowed values are:'
                    F'- [O] - Optional\n'
                    F'- [H] - Hidden\n'
                    F'- [M] - Mandatory\n'
                    F'Contact Administrator to fix this.'
                )
            if control == 'O':
                return
            elif control == 'H':
                if payload.get(field_name):
                    raise ObligatoryFieldValidationError(
                        F'Field {field_name} is set as hidden, but payload provides value. '
                        F'Does field {field_name} have default?')
            elif control == 'M' and not (payload.get(field_name)):
                raise ObligatoryFieldValidationError(F'Field {field_name} is mandatory, '
                                                     F'but payload does not provide value')


def validate_payload_for_obligatory_fields(list_of_obligatory_fields, payload_arg='data'):
    """
    Function decorator used for conveniently validate payload in functions.
    It creates instance of ObligatoryFieldValidation using list_of_obligatory_fields argument as obligatory
    characters and executes validation.
    :param list_of_obligatory_fields: List of obligatory fields for designated payload.
    :param payload_arg: Additional argument determining name of decorated function argument that provides payload.
    :return: None
    """

    def decorator(func):
        # Get index of payload arg in case it's not explicitly provided as kwarg.
        argspec = getfullargspec(func)
        argument_index = argspec.args.index(payload_arg)

        @functools.wraps(func)
        def wrapper_validate_fields(*args, **kwargs):
            try:
                value = args[argument_index]
            except IndexError:
                # Payload passed as kwarg not arg
                value = kwargs[payload_arg]

            validator = ObligatoryFieldValidation(list_of_obligatory_fields)
            validator.validate_obligatory_fields(value)
            out = func(*args, **kwargs)
            return out

        return wrapper_validate_fields

    return decorator
