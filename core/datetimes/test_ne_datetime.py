from django.test import TestCase
from datetime import date as py_date
from datetime import date as py_date
from datetime import datetime as py_datetime
from .ne_datetime import date, datetime, timedelta


class DateTestCase(TestCase):
    def test_from_ad_date(self):
        ad_dt = py_date(2020, 1, 13)
        ne_dt = date.from_ad_date(ad_dt)
        self.assertEqual(ne_dt, date(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(ad_dt, looped_dt)

    def test_from_ad_datetime(self):
        ad_dt = py_datetime(2020, 1, 13, 11, 23, 42, 123987)
        ne_dt = date.from_ad_datetime(ad_dt)
        self.assertEqual(ne_dt, date(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(looped_dt, py_date(2020, 1, 13))

    def test_raw_iso_format(self):
        dt = date(2075, 12, 8)
        self.assertEquals("2075-12-08", dt.raw_isoformat())

    def test_ad_iso_format(self):
        dt = date(2075, 12, 8)
        self.assertEquals("2019-03-22", dt.ad_isoformat())

    def test_add_days(self):
        dt = date(2075, 10, 22)
        dt_plus = dt + timedelta(days=14)
        self.assertEquals(date(2075, 11, 7), dt_plus)


class DatetimeTestCase(TestCase):
    def test_from_ad_date(self):
        ad_dt = py_date(2020, 1, 13)
        ne_dt = datetime.from_ad_date(ad_dt)
        self.assertEqual(ne_dt, datetime(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(ad_dt, looped_dt)

    def test_from_ad_datetime(self):
        ad_dt = py_datetime(2020, 1, 13, 11, 23, 42, 123987)
        ne_dt = datetime.from_ad_datetime(ad_dt)
        self.assertEqual(ne_dt, datetime(2076, 9, 28, 11, 23, 42, 123987))
        looped_dt = ne_dt.to_ad_datetime()
        self.assertEqual(looped_dt, py_datetime(
            2020, 1, 13, 11, 23, 42, 123987))
