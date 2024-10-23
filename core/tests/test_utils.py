import os

from django.db import connections
from django.test import TestCase
from django.test.runner import DiscoverRunner
from django.test.utils import get_unique_databases_and_mirrors

from core.utils import comparable, full_class_name


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

        obj1 = A(f="a")
        obj2 = A(f="a")
        self.assertEquals(obj1, obj2)
        obj3 = B(f="b")
        self.assertNotEquals(obj1, obj3)
        obj4 = B(f="a")
        self.assertNotEquals(obj1, obj4)


class UtilsTestCase(TestCase):
    def test_full_class_name(self):
        self.assertEquals(full_class_name(self), "core.tests.test_utils.UtilsTestCase")

        self.assertEquals(full_class_name(1), "int")
