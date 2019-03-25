import sys
import importlib
import core
from django.test import TestCase
from datetime import date as py_date
from datetime import datetime as py_datetime
from .shared import datedelta


class DateTestCase(TestCase):
    def setUp(self):
        core.calendar = importlib.import_module(
            '.calendars.ad_calendar', 'core')
        core.datetime = importlib.import_module(
            '.datetimes.ad_datetime', 'core')

    def test_ad_date(self):
        py_dt = py_date(2020, 1, 13)
        ad_dt = core.datetime.date(2020, 1, 13)
        self.assertEqual(py_dt, ad_dt)

    def test_repr(self):
        ad_dt = core.datetime.date(2020, 1, 13)
        self.assertEqual(
            repr(ad_dt), 'core.datetimes.ad_datetime.date(2020, 1, 13)')

    def test_str(self):
        ad_dt = core.datetime.date(2020, 1, 13)
        self.assertEqual(str(ad_dt), '2020-01-13')

    def test_from_ad_datetime(self):
        db_dt = core.datetime.date.from_ad_datetime(py_datetime(2020, 1, 13))
        ad_dt = core.datetime.date(2020, 1, 13)
        self.assertEqual(db_dt, ad_dt)

    def test_to_ad_datetime(self):
        ad_dt = core.datetime.date(2020, 1, 13)
        db_dt = ad_dt.to_ad_datetime()
        self.assertEqual(db_dt, py_datetime(2020, 1, 13))

    def test_raw_iso_format(self):
        dt = core.datetime.date(2019, 3, 22)
        self.assertEquals("2019-03-22", dt.raw_isoformat())

    def test_ad_iso_format(self):
        dt = core.datetime.date(2019, 3, 22)
        self.assertEquals("2019-03-22", dt.ad_isoformat())

    def test_add_sub_years(self):
        dt = core.datetime.date(2020, 10, 22)
        self.assertEquals(core.datetime.date(2022, 10, 22), (dt + datedelta(years=2)))
        self.assertEquals(core.datetime.date(2018, 10, 22), (dt + datedelta(years=-2)))
        self.assertEquals(core.datetime.date(2022, 10, 22), (dt - datedelta(years=-2)))
        self.assertEquals(core.datetime.date(2018, 10, 22), (dt - datedelta(years=2)))

    def test_add_sub_months(self):
        dt = core.datetime.date(2020, 10, 22)
        self.assertEquals(core.datetime.date(2020, 12, 22), (dt + datedelta(months=2)))
        self.assertEquals(core.datetime.date(2020, 8, 22), (dt + datedelta(months=-2)))
        self.assertEquals(core.datetime.date(2020, 8, 22), (dt - datedelta(months=2)))
        self.assertEquals(core.datetime.date(2020, 12, 22), (dt - datedelta(months=-2)))

    def test_add_sub_days(self):
        dt = core.datetime.date(2019, 3, 22)
        self.assertEquals(core.datetime.date(2019, 4, 5), (dt + core.datetime.timedelta(days=14)))
        self.assertEquals(core.datetime.date(2019, 4, 5), (dt - core.datetime.timedelta(days= -14)))

        dt = core.datetime.date(2019, 3, 11)
        self.assertEquals(core.datetime.date(2019, 2, 25), (dt - core.datetime.timedelta(days=14)))
        self.assertEquals(core.datetime.date(2019, 2, 25), (dt + core.datetime.timedelta(days= -14)))

    def test_eq_gt_ge_lt_le(self):
        dt = core.datetime.date(2019, 3, 11)
        dt_bis = core.datetime.date(2019, 3, 11)
        dt_after = core.datetime.date(2019, 3, 12)
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
            '.calendars.ad_calendar', 'core')
        core.datetime = importlib.import_module(
            '.datetimes.ad_datetime', 'core')

    def test_ad_datetime(self):
        py_dt = py_datetime(2020, 1, 13, 10, 9, 55, 728267)
        ad_dt = core.datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)
        self.assertEqual(py_dt, ad_dt)

    def test_repr(self):
        ad_dt = core.datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)
        self.assertEqual(repr(
            ad_dt), 'core.datetimes.ad_datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)')

    def test_str(self):
        ad_dt = core.datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)
        self.assertEqual(str(ad_dt), '2020-01-13 10:09:55.728267')

    def test_add_sub_years(self):
        dt = core.datetime.datetime(2020, 10, 22, 14, 25, 44, 876134)
        self.assertEquals(
            core.datetime.datetime(2022, 10, 22, 14, 25, 44, 876134),
            (dt + datedelta(years=2)))
        self.assertEquals(
            core.datetime.datetime(2018, 10, 22, 14, 25, 44,876134),
            (dt + datedelta(years=-2)))
        self.assertEquals(
            core.datetime.datetime(2022, 10, 22, 14, 25, 44, 876134),
            (dt - datedelta(years=-2)))
        self.assertEquals(
            core.datetime.datetime(2018, 10, 22, 14, 25, 44, 876134),
            (dt - datedelta(years=2)))

    def test_add_sub_months(self):
        dt = core.datetime.datetime(2020, 10, 22, 14, 25, 44, 876134)
        self.assertEquals(
            core.datetime.datetime(2020, 12, 22, 14, 25, 44, 876134),
            (dt + datedelta(months=2)))
        self.assertEquals(
            core.datetime.datetime(2020, 8, 22, 14, 25, 44, 876134),
            (dt + datedelta(months=-2)))
        self.assertEquals(
            core.datetime.datetime(2020, 8, 22, 14, 25, 44, 876134),
            (dt - datedelta(months=2)))
        self.assertEquals(
            core.datetime.datetime(2020, 12, 22, 14, 25, 44, 876134),
            (dt - datedelta(months=-2)))

    def test_add_sub_days(self):
        dt = core.datetime.datetime(2019, 3, 22)
        self.assertEquals(core.datetime.datetime(2019, 4, 5),
                          (dt + core.datetime.timedelta(days=14)))
        self.assertEquals(core.datetime.datetime(2019, 4, 5),
                          (dt - core.datetime.timedelta(days=-14)))

        dt = core.datetime.datetime(2019, 3, 11)
        self.assertEquals(core.datetime.datetime(2019, 2, 25),
                          (dt - core.datetime.timedelta(days=14)))
        self.assertEquals(core.datetime.datetime(2019, 2, 25),
                          (dt + core.datetime.timedelta(days=-14)))

    def test_eq_gt_ge_lt_le(self):
        dt = core.datetime.datetime(2019, 3, 11)
        dt_bis = core.datetime.datetime(2019, 3, 11)
        dt_after = core.datetime.datetime(2019, 3, 12)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)