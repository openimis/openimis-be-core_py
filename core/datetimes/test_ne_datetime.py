import sys
import importlib
import core
from django.test import TestCase
from datetime import date as py_date
from datetime import date as py_date
from datetime import datetime as py_datetime
from .ne_datetime import date, datetime, timedelta
from .shared import datedelta


class DateTestCase(TestCase):
    def setUp(self):
        core.calendar = importlib.import_module(
            '.calendars.ne_calendar', 'core')
        core.datetime = importlib.import_module(
            '.datetimes.ne_datetime', 'core')

    def test_from_ad_date(self):
        ad_dt = py_date(2020, 1, 13)
        ne_dt = date.from_ad_date(ad_dt)
        self.assertEqual(ne_dt, date(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(ad_dt, looped_dt)

    def test_from_ad_datetime(self):
        ad_dt = py_datetime(2020, 1, 13, 11, 23, 42, 123987)
        ne_dt = core.datetime.date.from_ad_datetime(ad_dt)
        self.assertEqual(ne_dt, date(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(looped_dt, py_date(2020, 1, 13))

    def test_to_ad_date(self):
        ne_dt = core.datetime.date(2076, 9, 28)
        ad_dt = ne_dt.to_ad_date()
        py_dt = py_date(2020, 1, 13)
        self.assertEqual(ad_dt, py_dt)

    def test_to_ad_datetime(self):
        ne_dt = core.datetime.datetime(2076, 9, 28, 11, 22, 33, 444555)
        ad_dt = ne_dt.to_ad_datetime()
        py_dt = py_datetime(2020, 1, 13, 11, 22, 33, 444555)
        self.assertEqual(ad_dt, py_dt)

    def test_repr(self):
        self.assertEqual(repr(date(2076, 2, 32)),
                         'core.datetimes.ne_datetime.date(2076, 2, 32)')

    def test_str(self):
        self.assertEqual(str(date(2076, 2, 32)), '2076-02-32')

    def test_raw_iso_format(self):
        self.assertEquals("2076-02-32", date(2076, 2, 32).raw_isoformat())
        self.assertEquals("2076-04-01", date(2076, 4, 1).raw_isoformat())

    def test_ad_iso_format(self):
        self.assertEquals("2019-06-15", date(2076, 2, 32).ad_isoformat())

    def test_add_sub_years(self):
        dt = core.datetime.date(2075, 10, 22)
        self.assertEquals(core.datetime.date(2077, 10, 22), (dt + datedelta(years=2)))
        self.assertEquals(core.datetime.date(2073, 10, 22), (dt + datedelta(years=-2)))
        self.assertEquals(core.datetime.date(2077, 10, 22), (dt - datedelta(years=-2)))
        self.assertEquals(core.datetime.date(2073, 10, 22), (dt - datedelta(years=2)))

    def test_add_sub_months(self):
        dt = core.datetime.date(2075, 10, 22)
        self.assertEquals(core.datetime.date(2075, 12, 22), (dt + datedelta(months=2)))
        self.assertEquals(core.datetime.date(2075, 8, 22), (dt + datedelta(months= -2)))
        self.assertEquals(core.datetime.date(2075, 8, 22), (dt - datedelta(months=2)))
        self.assertEquals(core.datetime.date(2075, 12, 22), (dt - datedelta(months= -2)))

    def test_add_sub_days(self):
        dt = core.datetime.date(2075, 10, 22)
        self.assertEquals(core.datetime.date(2075, 11, 7), (dt + core.datetime.timedelta(days=14)))
        self.assertEquals(core.datetime.date(2075, 11, 7), (dt - core.datetime.timedelta(days=- 14)))

        dt = core.datetime.date(2075, 10, 11)
        self.assertEquals(core.datetime.date(2075, 9, 27), (dt + core.datetime.timedelta(days=-14)))
        self.assertEquals(core.datetime.date(2075, 9, 27), (dt - core.datetime.timedelta(days=14)))

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
    def setUp(self):
        core.calendar = importlib.import_module(
            '.calendars.ne_calendar', 'core')
        core.datetime = importlib.import_module(
            '.datetimes.ne_datetime', 'core')

    def test_from_ad_date(self):
        ad_dt = py_date(2020, 1, 13)
        ne_dt = core.datetime.datetime.from_ad_date(ad_dt)
        self.assertEqual(ne_dt, core.datetime.datetime(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(ad_dt, looped_dt)

    def test_from_ad_datetime(self):
        ad_dt = py_datetime(2020, 1, 13, 11, 23, 42, 123987)
        ne_dt = core.datetime.datetime.from_ad_datetime(ad_dt)
        self.assertEqual(ne_dt, core.datetime.datetime(2076, 9, 28, 11, 23, 42, 123987))
        looped_dt = ne_dt.to_ad_datetime()
        self.assertEqual(looped_dt, py_datetime(
            2020, 1, 13, 11, 23, 42, 123987))

    def test_to_ad_date(self):
        ne_dt = core.datetime.datetime(2076, 9, 28, 11, 22, 33, 444555)
        ad_dt = ne_dt.to_ad_date()
        py_dt = py_date(2020, 1, 13)
        self.assertEqual(ad_dt, py_dt)

    def test_to_ad_datetime(self):
        ne_dt = core.datetime.datetime(2076, 9, 28, 11, 22, 33, 444555)
        ad_dt = ne_dt.to_ad_datetime()
        py_dt = py_datetime(2020, 1, 13, 11, 22, 33, 444555)
        self.assertEqual(ad_dt, py_dt)

    def test_repr(self):
        ad_dt = core.datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)
        self.assertEqual(repr(
            ad_dt), 'core.datetimes.ne_datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)')

    def test_str(self):
        ad_dt = core.datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)
        self.assertEqual(str(ad_dt), '2020-01-13 10:09:55.728267')

    def test_add_sub_years(self):
        dt = core.datetime.datetime(2075, 10, 22, 5, 33, 24, 786222)
        self.assertEquals(core.datetime.datetime(2077, 10, 22, 5, 33, 24,
                                   786222), (dt + datedelta(years=2)))
        self.assertEquals(core.datetime.datetime(2073, 10, 22, 5, 33, 24,
                                   786222), (dt + datedelta(years=-2)))
        self.assertEquals(core.datetime.datetime(2077, 10, 22, 5, 33, 24,
                                   786222), (dt - datedelta(years=-2)))
        self.assertEquals(core.datetime.datetime(2073, 10, 22, 5, 33, 24,
                                   786222), (dt - datedelta(years=2)))

    def test_add_sub_months(self):
        dt = core.datetime.datetime(2075, 10, 22, 5, 33, 24, 786222)
        self.assertEquals(core.datetime.datetime(2075, 12, 22, 5, 33, 24, 786222), (dt + datedelta(months=2)))
        self.assertEquals(core.datetime.datetime(2075, 8, 22, 5, 33, 24, 786222), (dt + datedelta(months= -2)))
        self.assertEquals(core.datetime.datetime(2075, 8, 22, 5, 33, 24, 786222), (dt - datedelta(months=2)))
        self.assertEquals(core.datetime.datetime(2075, 12, 22, 5, 33, 24, 786222), (dt - datedelta(months= -2)))

    def test_add_sub_days(self):
        dt = date(2075, 10, 22)
        self.assertEquals(date(2075, 11, 7), (dt + timedelta(days=14)))
        self.assertEquals(date(2075, 11, 7), (dt - timedelta(days=-14)))

        dt = date(2075, 10, 11)
        self.assertEquals(date(2075, 9, 27), (dt - timedelta(days=14)))
        self.assertEquals(date(2075, 9, 27), (dt + timedelta(days=-14)))

    def test_date_eq_gt_ge_lt_le(self):
        dt = core.datetime.datetime(2076, 3, 11)
        dt_bis = core.datetime.datetime(2076, 3, 11)
        dt_after = core.datetime.datetime(2076, 3, 12)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)

    def test_datetime_eq_gt_ge_lt_le(self):
        dt = core.datetime.datetime(2076, 3, 11, 11, 12, 13, 567999)
        dt_bis = core.datetime.datetime(2076, 3, 11, 11, 12, 13, 567999)
        dt_after = core.datetime.datetime(2076, 3, 11, 11, 12, 13, 568999)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)
