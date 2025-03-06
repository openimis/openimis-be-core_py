import os
import datetime
import uuid
import decimal
from django.test import TestCase
from django.db import connections
from django.test.runner import DiscoverRunner
from django.test.utils import get_unique_databases_and_mirrors

from core.utils import full_class_name, comparable, to_json_safe_value
from core.datetimes.ad_datetime import AdDate, AdDatetime


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
            self), 'core.tests.test_utils.UtilsTestCase')

        self.assertEquals(full_class_name(
            1), 'int')

    def test_json_serialize_value(self):
        self.assertEquals(to_json_safe_value(42), 42)
        self.assertEquals(to_json_safe_value("foo"), "foo")

        uuid_obj = uuid.uuid4()
        self.assertEquals(to_json_safe_value(uuid_obj), str(uuid_obj))

        date_obj = datetime.date(2025, 1, 1)
        self.assertEquals(to_json_safe_value(date_obj), str(date_obj))

        ad_date_obj = AdDate(2025, 1, 1)
        self.assertEquals(to_json_safe_value(ad_date_obj), str(ad_date_obj))

        ad_datetime_obj = AdDatetime(2025, 1, 1, 12, 0, 0)
        self.assertEquals(to_json_safe_value(ad_datetime_obj), str(ad_datetime_obj))

        decimal_obj = decimal.Decimal("12345.6789")
        self.assertEquals(to_json_safe_value(decimal_obj), str(decimal_obj))
