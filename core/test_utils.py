from django.test import TestCase
from django.test.runner import DiscoverRunner

from .utils import full_class_name, comparable


class UnManagedModelTestRunner(DiscoverRunner):

    def setup_test_environment(self, *args, **kwargs):
        from django.apps import apps
        get_models = apps.get_models
        self.unmanaged_models = [
            m for m in get_models() if not m._meta.managed]
        for m in self.unmanaged_models:
            m._meta.managed = True
        super(UnManagedModelTestRunner,
              self).setup_test_environment(*args, **kwargs)

    def teardown_test_environment(self, *args, **kwargs):
        super(UnManagedModelTestRunner,
              self).teardown_test_environment(*args, **kwargs)
        for m in self.unmanaged_models:
            m._meta.managed = False


class ComparableTest(TestCase):
    def test_generic_eq(self):
        @comparable
        class A(object):
            def __init__(self, f):
                self.f = f

            def __eq__(self, other):
                return self.f == other.f

        @comparable
        class B(object):
            def __init__(self, f):
                self.f = f

            def __eq__(self, other):
                return self.f == other.f

        obj1 = A(f='a')
        obj2 = A(f='a')
        self.assertEquals(obj1, obj2)
        obj3 = B(f='b')
        self.assertNotEquals(obj1, obj3)
        obj4 = B(f='a')
        self.assertNotEquals(obj1, obj4)


class UtilsTestCase(TestCase):
    def test_full_class_name(self):
        self.assertEquals(full_class_name(
            self), 'core.test_utils.UtilsTestCase')

        self.assertEquals(full_class_name(
            1), 'int')

