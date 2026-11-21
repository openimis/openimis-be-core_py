import enum


def enum_values(value):
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        # Input objects arrive as dict subclasses whose fields are also attributes,
        # which can shadow dict methods (a field named "items"): use dict's own
        # methods, and update the attribute along with the key.
        for key, item in list(dict.items(value)):
            converted = enum_values(item)
            if converted is not item:
                dict.__setitem__(value, key, converted)
                if type(value) is not dict:
                    setattr(value, key, converted)
        return value
    if isinstance(value, list):
        return [enum_values(item) for item in value]
    return value
