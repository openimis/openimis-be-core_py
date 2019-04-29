import sys
import importlib
import core
from django.test import TestCase
from datetime import date as py_date
from datetime import datetime as py_datetime
from .shared import is_midnight, datetimedelta


class SharedUtilsTest(TestCase):
    def setUp(self):
        core.calendar = importlib.import_module(
            '.calendars.ad_calendar', 'core')
        core.datetime = importlib.import_module(
            '.datetimes.ad_datetime', 'core')

    def test_is_midnight(self):
        self.assertTrue(is_midnight(
            core.datetime.datetime(2019, 4, 29, 0, 0, 0, 0)))
        self.assertTrue(is_midnight(core.datetime.date(2019, 4, 29)))
        self.assertFalse(is_midnight(
            core.datetime.datetime(2019, 4, 29, 11, 23, 56, 987654)))
        self.assertFalse(is_midnight(
            core.datetime.datetime(2019, 4, 29, 0, 23, 56, 987654)))
        self.assertFalse(is_midnight(
            core.datetime.datetime(2019, 4, 29, 0, 0, 56, 987654)))
        self.assertFalse(is_midnight(
            core.datetime.datetime(2019, 4, 29, 0, 0, 0, 987654)))

class AdDateTestCase(TestCase):
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

        self.assertIsNone(core.datetime.date.from_ad_datetime(None))

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
        self.assertEquals(core.datetime.date(2022, 10, 22),
                          (dt + datetimedelta(years=2)))
        self.assertEquals(core.datetime.date(2018, 10, 22),
                          (dt + datetimedelta(years=-2)))
        self.assertEquals(core.datetime.date(2022, 10, 22),
                          (dt - datetimedelta(years=-2)))
        self.assertEquals(core.datetime.date(2018, 10, 22),
                          (dt - datetimedelta(years=2)))

    def test_add_sub_months(self):
        dt = core.datetime.date(2020, 10, 22)
        self.assertEquals(core.datetime.date(2020, 12, 22),
                          (dt + datetimedelta(months=2)))
        self.assertEquals(core.datetime.date(2020, 8, 22),
                          (dt + datetimedelta(months=-2)))
        self.assertEquals(core.datetime.date(2020, 8, 22),
                          (dt - datetimedelta(months=2)))
        self.assertEquals(core.datetime.date(2020, 12, 22),
                          (dt - datetimedelta(months=-2)))

    def test_add_sub_days(self):
        dt = core.datetime.date(2019, 3, 22)
        self.assertEquals(core.datetime.date(2019, 4, 5),
                          (dt + datetimedelta(days=14)))
        self.assertEquals(core.datetime.date(2019, 4, 5),
                          (dt - datetimedelta(days=-14)))

        dt = core.datetime.date(2019, 3, 11)
        self.assertEquals(core.datetime.date(2019, 2, 25),
                          (dt - datetimedelta(days=14)))
        self.assertEquals(core.datetime.date(2019, 2, 25),
                          (dt + datetimedelta(days=-14)))

    def test_add_sub_mixed(self):
        dt = core.datetime.date(2020, 10, 22)
        self.assertEquals(
            core.datetime.date(2020, 12, 6),
            (dt + datetimedelta(months=1, days=14)))
        self.assertEquals(
            core.datetime.date(2021, 2, 28),
            (dt + 4 * datetimedelta(months=1, days=1, hours=14, seconds=36)))
        self.assertEquals(
            core.datetime.datetime(2020, 10, 22),
            (dt + datetimedelta(days=-1, hours=24)))
        self.assertEquals(
            core.datetime.date(2021, 2, 20),
            (dt + 4 * datetimedelta(months=1, days=-1, hours=14, seconds=36)))

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

    def test_diff(self):
        ad_dt_1 = core.datetime.date(2019, 12, 7)
        ad_dt_2 = core.datetime.date(2019, 12, 8)
        self.assertEqual(ad_dt_2 - ad_dt_1, datetimedelta(days=1))

        ad_dt_1 = core.datetime.date(2019, 12, 7)
        ad_dt_2 = core.datetime.date(2020, 1, 7)
        self.assertEqual(ad_dt_2 - ad_dt_1, datetimedelta(days=31))


class AdDatetimeTestCase(TestCase):
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
            (dt + datetimedelta(years=2)))
        self.assertEquals(
            core.datetime.datetime(2018, 10, 22, 14, 25, 44, 876134),
            (dt + datetimedelta(years=-2)))
        self.assertEquals(
            core.datetime.datetime(2022, 10, 22, 14, 25, 44, 876134),
            (dt - datetimedelta(years=-2)))
        self.assertEquals(
            core.datetime.datetime(2018, 10, 22, 14, 25, 44, 876134),
            (dt - datetimedelta(years=2)))

    def test_add_sub_months(self):
        dt = core.datetime.datetime(2020, 10, 22, 14, 25, 44, 876134)
        self.assertEquals(
            core.datetime.datetime(2020, 12, 22, 14, 25, 44, 876134),
            (dt + datetimedelta(months=2)))
        self.assertEquals(
            core.datetime.datetime(2020, 8, 22, 14, 25, 44, 876134),
            (dt + datetimedelta(months=-2)))
        self.assertEquals(
            core.datetime.datetime(2020, 8, 22, 14, 25, 44, 876134),
            (dt - datetimedelta(months=2)))
        self.assertEquals(
            core.datetime.datetime(2020, 12, 22, 14, 25, 44, 876134),
            (dt - datetimedelta(months=-2)))

    def test_add_sub_days(self):
        dt = core.datetime.datetime(2019, 3, 22)
        self.assertEquals(core.datetime.datetime(2019, 4, 5),
                          (dt + datetimedelta(days=14)))
        self.assertEquals(core.datetime.datetime(2019, 4, 5),
                          (dt - datetimedelta(days=-14)))

        dt = core.datetime.datetime(2019, 3, 11)
        self.assertEquals(core.datetime.datetime(2019, 2, 25),
                          (dt - datetimedelta(days=14)))
        self.assertEquals(core.datetime.datetime(2019, 2, 25),
                          (dt + datetimedelta(days=-14)))

    def test_add_sub_mixed(self):
        dt = core.datetime.datetime(2019, 10, 22, 5, 33, 24, 786222)
        self.assertEquals(
            core.datetime.datetime(2019, 12, 6, 5, 33, 24, 786222),
            (dt + datetimedelta(months=1, days=14)))
        self.assertEquals(
            core.datetime.datetime(2020, 2, 28, 13, 35, 48, 786222),
            (dt + 4 * datetimedelta(months=1, days=1, hours=14, seconds=36)))
        self.assertEquals(
            core.datetime.datetime(2019, 10, 22, 5, 33, 24, 786222),
            (dt + datetimedelta(days=-1, hours=24)))
        self.assertEquals(
            core.datetime.datetime(2020, 2, 20, 13, 35, 48, 786222),
            (dt + 4 * datetimedelta(months=1, days=-1, hours=14, seconds=36)))

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

    def test_diff(self):
        ne_dt_1 = core.datetime.datetime(2019, 12, 7)
        ne_dt_2 = core.datetime.datetime(2019, 12, 8)
        self.assertEqual(ne_dt_2 - ne_dt_1, datetimedelta(days=1))

        ne_dt_1 = core.datetime.datetime(2019, 12, 7, 11, 5, 34, 999999)
        ne_dt_2 = core.datetime.datetime(2020, 1, 7, 11, 7, 34, 999999)
        self.assertEqual(ne_dt_2 - ne_dt_1,
                         datetimedelta(days=31, minutes=2))
