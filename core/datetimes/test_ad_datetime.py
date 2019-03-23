from django.test import TestCase
from datetime import date as py_date
from datetime import datetime as py_datetime
from .ad_datetime import date, datetime, timedelta


class DateTestCase(TestCase):
    def test_ad_date(self):
        py_dt = py_date(2020, 1, 13)
        ad_dt = date(2020, 1, 13)
        self.assertEqual(py_dt, ad_dt)

    def test_from_ad_datetime(self):
        db_dt = date.from_ad_datetime(py_datetime(2020, 1, 13))
        ad_dt = date(2020, 1, 13)
        self.assertEqual(db_dt, ad_dt)

    def test_to_ad_datetime(self):
        ad_dt = date(2020, 1, 13)
        db_dt = ad_dt.to_ad_datetime()
        self.assertEqual(db_dt, py_datetime(2020, 1, 13))

    def test_raw_iso_format(self):
        dt = date(2019, 3, 22)
        self.assertEquals("2019-03-22", dt.raw_isoformat())

    def test_ad_iso_format(self):
        dt = date(2019, 3, 22)
        self.assertEquals("2019-03-22", dt.ad_isoformat())

    def test_add_days(self):
        dt = date(2019, 3, 22)
        dt_plus = dt + timedelta(days=14)
        self.assertEquals(date(2019, 4, 5), dt_plus)

    def test_sub_days(self):
        dt = date(2019, 3, 11)
        dt_plus = dt - timedelta(days=14)
        self.assertEquals(date(2019, 2, 25), dt_plus)

    def test_eq_gt_ge_lt_le(self):
        dt = date(2019, 3, 11)
        dt_bis = date(2019, 3, 11)
        dt_after = date(2019, 3, 12)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)

class DatetimeTestCase(TestCase):
    def test_ad_datetime(self):
        py_dt = py_datetime(2020, 1, 13, 10, 9, 55, 728267)
        ad_dt = datetime(2020, 1, 13, 10, 9, 55, 728267)
        self.assertEqual(py_dt, ad_dt)

    def test_add_days(self):
        dt = datetime(2019, 3, 22)
        dt_plus = dt + timedelta(days=14)
        self.assertEquals(datetime(2019, 4, 5), dt_plus)

    def test_sub_days(self):
        dt = datetime(2019, 3, 11)
        dt_plus = dt - timedelta(days=14)
        self.assertEquals(datetime(2019, 2, 25), dt_plus)

    def test_eq_gt_ge_lt_le(self):
        dt = datetime(2019, 3, 11)
        dt_bis = datetime(2019, 3, 11)
        dt_after = datetime(2019, 3, 12)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)
