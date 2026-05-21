from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import ModuleConfiguration
from core.module_config_registry import (
    _validators,
    _reloaders,
    _key,
    register_validator,
    register_reloader,
    validate_module_configuration,
    reload_module_configuration,
)


def _noop(instance):
    pass


def _noop_alt(instance):
    pass


class ModuleConfigRegistryTest(TestCase):

    def setUp(self):
        self._saved_validators = dict(_validators)
        self._saved_reloaders = dict(_reloaders)

    def tearDown(self):
        _validators.clear()
        _validators.update(self._saved_validators)
        _reloaders.clear()
        _reloaders.update(self._saved_reloaders)

    def test_register_validator(self):
        register_validator("test_module", _noop)
        self.assertIn(_noop, _validators[_key("test_module")])

    def test_register_reloader(self):
        register_reloader("test_module", _noop)
        self.assertIn(_noop, _reloaders[_key("test_module")])

    def test_no_duplicate_registration(self):
        register_validator("test_module", _noop)
        register_validator("test_module", _noop)
        self.assertEqual(_validators[_key("test_module")].count(_noop), 1)

    def test_layer_isolation(self):
        register_validator("test_module", _noop, layer="be")
        register_validator("test_module", _noop_alt, layer="fe")
        self.assertIn(_noop, _validators[_key("test_module", "be")])
        self.assertIn(_noop_alt, _validators[_key("test_module", "fe")])
        self.assertNotIn(_noop_alt, _validators[_key("test_module", "be")])

    def test_validate_calls_matching_validators(self):
        calls = []
        register_validator("mod_a", lambda inst: calls.append("a"))
        register_validator("mod_b", lambda inst: calls.append("b"))

        instance = ModuleConfiguration(module="mod_a", layer="be", version="1", config="{}")
        validate_module_configuration(instance)
        self.assertEqual(calls, ["a"])

    def test_reload_calls_matching_reloaders(self):
        calls = []
        register_reloader("mod_a", lambda inst: calls.append("a"))
        register_reloader("mod_b", lambda inst: calls.append("b"))

        instance = ModuleConfiguration(module="mod_a", layer="be", version="1", config="{}")
        reload_module_configuration(instance)
        self.assertEqual(calls, ["a"])

    def test_validate_propagates_validation_error(self):
        def bad_validator(instance):
            raise ValidationError("bad config")

        register_validator("mod_x", bad_validator)
        instance = ModuleConfiguration(module="mod_x", layer="be", version="1", config="{}")

        with self.assertRaises(ValidationError):
            validate_module_configuration(instance)

    def test_no_validators_for_module_is_noop(self):
        instance = ModuleConfiguration(module="unregistered", layer="be", version="1", config="{}")
        validate_module_configuration(instance)
        reload_module_configuration(instance)

    def test_save_rejects_invalid_json(self):
        mc = ModuleConfiguration(module="test", layer="be", version="1", config="{bad")
        with self.assertRaises(ValidationError):
            mc.save()
        self.assertFalse(ModuleConfiguration.objects.filter(pk=mc.pk).exists())

    def test_save_validates_before_persist(self):
        def reject_all(instance):
            raise ValidationError("blocked")

        register_validator("save_test", reject_all)
        mc = ModuleConfiguration(module="save_test", layer="be", version="1", config="{}")

        with self.assertRaises(ValidationError):
            mc.save()

        self.assertFalse(ModuleConfiguration.objects.filter(pk=mc.pk).exists())

    def test_save_reloads_after_commit(self):
        reloaded = []
        register_reloader("reload_test", lambda inst: reloaded.append(inst.module))

        mc = ModuleConfiguration(module="reload_test", layer="be", version="1", config="{}")
        with self.captureOnCommitCallbacks(execute=True):
            mc.save()
        self.assertEqual(reloaded, ["reload_test"])
        mc.delete()
