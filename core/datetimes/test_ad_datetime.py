from django.test import TestCase
from datetime import date as py_date
from .ad_datetime import date


class DateTestCase(TestCase):
    def test_from_ad_date(self):
        py_dt = py_date(2020, 1, 13)
        ad_dt = date(2020, 1, 13)
        self.assertEqual(py_dt, ad_dt)