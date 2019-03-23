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

    def test_sub_days(self):
        dt = date(2075, 10, 11)
        dt_plus = dt - timedelta(days=14)
        self.assertEquals(date(2075, 9, 27), dt_plus)

    def test_eq_gt_ge_lt_le(self):
        dt = date(2076, 3, 11)
        dt_bis = date(2076, 3, 11)
        dt_after = date(2076, 3, 12)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)



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

    def test_to_ad_date(self):
        ne_dt = datetime(2076, 9, 28, 11, 22, 33, 444555)
        ad_dt = ne_dt.to_ad_date()
        py_dt = py_date(2020, 1, 13)
        self.assertEqual(ad_dt, py_dt)

    def test_to_ad_datetime(self):
        ne_dt = datetime(2076, 9, 28, 11, 22, 33, 444555)
        ad_dt = ne_dt.to_ad_datetime()
        py_dt = py_datetime(2020, 1, 13, 11, 22, 33, 444555)
        self.assertEqual(ad_dt, py_dt)

    def test_add_days(self):
        dt = date(2075, 10, 22)
        dt_plus = dt + timedelta(days=14)
        self.assertEquals(date(2075, 11, 7), dt_plus)

    def test_sub_days(self):
        dt = date(2075, 10, 11)
        dt_plus = dt - timedelta(days=14)
        self.assertEquals(date(2075, 9, 27), dt_plus)

    def test_date_eq_gt_ge_lt_le(self):
        dt = datetime(2076, 3, 11)
        dt_bis = datetime(2076, 3, 11)
        dt_after = datetime(2076, 3, 12)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)

    def test_datetime_eq_gt_ge_lt_le(self):
        dt = datetime(2076, 3, 11, 11, 12, 13, 567999)
        dt_bis = datetime(2076, 3, 11, 11, 12, 13, 567999)
        dt_after = datetime(2076, 3, 11, 11, 12, 13, 568999)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)