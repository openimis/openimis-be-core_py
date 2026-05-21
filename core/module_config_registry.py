_validators = {}
_reloaders = {}


def _key(module, layer="be"):
    return (module, layer)


def register_validator(module, fn, layer="be"):
    key = _key(module, layer)
    if fn not in _validators.setdefault(key, []):
        _validators[key].append(fn)


def register_reloader(module, fn, layer="be"):
    key = _key(module, layer)
    if fn not in _reloaders.setdefault(key, []):
        _reloaders[key].append(fn)


def validate_module_configuration(instance):
    for fn in _validators.get(_key(instance.module, instance.layer), []):
        fn(instance)


def reload_module_configuration(instance):
    for fn in _reloaders.get(_key(instance.module, instance.layer), []):
        fn(instance)
