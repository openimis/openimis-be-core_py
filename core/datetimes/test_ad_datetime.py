from django.test import TestCase
from datetime import date as py_date
from .ad_datetime import date, timedelta


class DateTestCase(TestCase):
    def test_from_ad_date(self):
        py_dt = py_date(2020, 1, 13)
        ad_dt = date(2020, 1, 13)
        self.assertEqual(py_dt, ad_dt)

    def test_raw_iso_format(self):
        dt = date(2019,3,22)
        self.assertEquals("2019-03-22", dt.raw_isoformat())

    def test_ad_iso_format(self):
        dt = date(2019,3,22)
        self.assertEquals("2019-03-22", dt.ad_isoformat())

    def test_add_days(self):
        dt = date(2019,3,22)
        dt_plus = dt + timedelta(days=14)
        self.assertEquals(date(2019,4,5), dt_plus)