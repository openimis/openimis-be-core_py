import sys
import importlib
import core
from django.test import TestCase
from datetime import date as py_date
from datetime import datetime as py_datetime
from .shared import is_midnight, datetimedelta


class NeDateTestCase(TestCase):
    def setUp(self):
        core.calendar = importlib.import_module(
            '.calendars.ne_calendar', 'core')
        core.datetime = importlib.import_module(
            '.datetimes.ne_datetime', 'core')

    def tearDown(self):
        core.calendar = importlib.import_module(
            '.calendars.ad_calendar', 'core')
        core.datetime = importlib.import_module(
            '.datetimes.ad_datetime', 'core')

    def test_today(self):
        ad_today = py_date.today()
        ne_today = core.datetime.date.today()
        self.assertEquals(ne_today, core.datetime.date.from_ad_date(ad_today))

    def test_from_ad_date(self):
        ad_dt = py_date(2020, 1, 13)       
        ne_dt = core.datetime.date.from_ad_date(ad_dt)
        self.assertEqual(ne_dt, core.datetime.date(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(ad_dt, looped_dt)

        self.assertIsNone(core.datetime.date.from_ad_date(None))

        #it also work if you give a datetime instead of a date...
        ad_dt = py_datetime(2020, 1, 13)       
        ne_dt = core.datetime.date.from_ad_date(ad_dt)
        self.assertEqual(ne_dt, core.datetime.date(2076, 9, 28))
        looped_dt = ne_dt.to_ad_datetime()
        self.assertEqual(ad_dt, looped_dt)

    def test_from_ad_datetime(self):
        ad_dt = py_datetime(2020, 1, 13, 11, 23, 42, 123987)
        ne_dt = core.datetime.date.from_ad_datetime(ad_dt)
        self.assertEqual(ne_dt, core.datetime.date(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(looped_dt, py_date(2020, 1, 13))

        self.assertIsNone(core.datetime.date.from_ad_datetime(None))        

    def test_to_ad_date(self):
        ne_dt = core.datetime.date(2076, 9, 28)
        ad_dt = ne_dt.to_ad_date()
        py_dt = py_date(2020, 1, 13)
        self.assertEqual(ad_dt, py_dt)

    def test_to_ad_datetime(self):
        ne_dt = core.datetime.date(2076, 9, 28)
        ad_dt = ne_dt.to_ad_datetime()
        py_dt = py_datetime(2020, 1, 13, 0, 0, 0, 0)
        self.assertEqual(ad_dt, py_dt)

    def test_repr(self):
        self.assertEqual(repr(core.datetime.date(2076, 2, 32)),
                         'core.datetimes.ne_datetime.date(2076, 2, 32)')

    def test_str(self):
        self.assertEqual(str(core.datetime.date(2076, 2, 32)), '2076-02-32')
        self.assertEqual(core.datetime.date(
            2076, 2, 32).displaylongformat(), 'शनिवार ३२ जेठ २०७६')
        self.assertEqual(core.datetime.date(
            2076, 2, 32).displayshortformat(), '३२/२/२०७६')

    def test_iso_format(self):
        self.assertEquals(
            "2076-02-32", core.datetime.date(2076, 2, 32).raw_isoformat())
        self.assertEquals(
            "2076-04-01", core.datetime.date(2076, 4, 1).raw_isoformat())
        self.assertEquals(
            "2019-06-15", core.datetime.date(2076, 2, 32).ad_isoformat())
        self.assertEquals(
            "2019-06-15", core.datetime.date(2076, 2, 32).isoformat())

    def test_add_sub_years(self):
        dt = core.datetime.date(2075, 10, 22)
        self.assertEquals(core.datetime.date(2077, 10, 22),
                          (dt + datetimedelta(years=2)))
        self.assertEquals(core.datetime.date(2073, 10, 22),
                          (dt + datetimedelta(years=-2)))
        self.assertEquals(core.datetime.date(2077, 10, 22),
                          (dt - datetimedelta(years=-2)))
        self.assertEquals(core.datetime.date(2073, 10, 22),
                          (dt - datetimedelta(years=2)))

    def test_add_sub_months(self):
        dt = core.datetime.date(2075, 10, 22)
        self.assertEquals(core.datetime.date(2075, 12, 22),
                          (dt + datetimedelta(months=2)))
        self.assertEquals(core.datetime.date(2075, 8, 22),
                          (dt + datetimedelta(months=-2)))
        self.assertEquals(core.datetime.date(2075, 8, 22),
                          (dt - datetimedelta(months=2)))
        self.assertEquals(core.datetime.date(2075, 12, 22),
                          (dt - datetimedelta(months=-2)))

    def test_add_sub_days(self):
        dt = core.datetime.date(2075, 10, 22)
        self.assertEquals(core.datetime.date(2075, 11, 7),
                          (dt + datetimedelta(days=14)))
        self.assertEquals(core.datetime.date(2075, 11, 7),
                          (dt - datetimedelta(days=- 14)))

        dt = core.datetime.date(2075, 10, 11)
        self.assertEquals(core.datetime.date(2075, 9, 27),
                          (dt + datetimedelta(days=-14)))
        self.assertEquals(core.datetime.date(2075, 9, 27),
                          (dt - datetimedelta(days=14)))

    def test_add_sub_mixed(self):
        dt = core.datetime.date(2075, 10, 22)
        self.assertEquals(
            core.datetime.date(2075, 12, 6),
            (dt + datetimedelta(months=1, days=14)))
        self.assertEquals(
            core.datetime.date(2076, 2, 28),
            (dt + 4 * datetimedelta(months=1, days=1, hours=14, seconds=36)))
        self.assertEquals(
            core.datetime.datetime(2075, 10, 22),
            (dt + datetimedelta(days=-1, hours=24)))
        self.assertEquals(
            core.datetime.date(2076, 2, 21),
            (dt + 4 * datetimedelta(months=1, days=-1, hours=14, seconds=36)))

    def test_eq_gt_ge_lt_le(self):
        dt = core.datetime.date(2076, 3, 11)
        dt_bis = core.datetime.date(2076, 3, 11)
        dt_after = core.datetime.date(2076, 3, 12)
        self.assertTrue(dt == dt_bis)
        self.assertTrue(dt >= dt_bis)
        self.assertTrue(dt <= dt_bis)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertTrue(dt_after > dt)
        self.assertTrue(dt_after >= dt)

    def test_min_max_date(self):
        self.assertEqual(core.datetime.date.min,
                         core.datetime.date.from_ad_date(py_date(1, 1, 1)))
        self.assertEqual(core.datetime.date.max,
                         core.datetime.date.from_ad_date(py_date(9999, 12, 31)))

    def test_diff(self):
        ne_dt_1 = core.datetime.date(2075, 12, 7)
        ne_dt_2 = core.datetime.date(2075, 12, 8)
        self.assertEqual(ne_dt_2 - ne_dt_1, datetimedelta(days=1))

        ne_dt_1 = core.datetime.date(2075, 12, 7)
        ne_dt_2 = core.datetime.date(2076, 1, 7)
        self.assertEqual(ne_dt_2 - ne_dt_1, datetimedelta(days=30))


class NeDatetimeTestCase(TestCase):
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

        self.assertIsNone(core.datetime.datetime.from_ad_date(None))

    def test_from_ad_datetime(self):
        ad_dt = py_datetime(2020, 1, 13, 11, 23, 42, 123987)
        ne_dt = core.datetime.datetime.from_ad_datetime(ad_dt)
        self.assertEqual(ne_dt, core.datetime.datetime(
            2076, 9, 28, 11, 23, 42, 123987))
        looped_dt = ne_dt.to_ad_datetime()
        self.assertEqual(looped_dt, py_datetime(
            2020, 1, 13, 11, 23, 42, 123987))

        self.assertIsNone(core.datetime.datetime.from_ad_datetime(None))

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
        self.assertEqual(
            repr(ad_dt),
            'core.datetimes.ne_datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)')

    def test_str(self):
        ad_dt = core.datetime.datetime(2020, 1, 13, 10, 9, 55, 728267)
        self.assertEqual(str(ad_dt), '2020-01-13 10:09:55.728267')

    def test_iso_format(self):
        self.assertEquals(
            "2019-06-15 11:22:33.444444", core.datetime.datetime(2076, 2, 32, 11, 22, 33, 444444).isoformat())        

    def test_add_sub_years(self):
        dt = core.datetime.datetime(2075, 10, 22, 5, 33, 24, 786222)
        self.assertEquals(
            core.datetime.datetime(2077, 10, 22, 5, 33, 24, 786222),
            (dt + datetimedelta(years=2)))
        self.assertEquals(
            core.datetime.datetime(2073, 10, 22, 5, 33, 24, 786222),
            (dt + datetimedelta(years=-2)))
        self.assertEquals(
            core.datetime.datetime(2077, 10, 22, 5, 33, 24, 786222),
            (dt - datetimedelta(years=-2)))
        self.assertEquals(
            core.datetime.datetime(2073, 10, 22, 5, 33, 24, 786222),
            (dt - datetimedelta(years=2)))

    def test_add_sub_months(self):
        dt = core.datetime.datetime(2075, 10, 22, 5, 33, 24, 786222)
        self.assertEquals(
            core.datetime.datetime(2075, 12, 22, 5, 33, 24, 786222),
            (dt + datetimedelta(months=2)))
        self.assertEquals(
            core.datetime.datetime(2075, 8, 22, 5, 33, 24, 786222),
            (dt + datetimedelta(months=-2)))
        self.assertEquals(
            core.datetime.datetime(2075, 8, 22, 5, 33, 24, 786222),
            (dt - datetimedelta(months=2)))
        self.assertEquals(
            core.datetime.datetime(2075, 12, 22, 5, 33, 24, 786222),
            (dt - datetimedelta(months=-2)))

    def test_add_sub_days(self):
        dt = core.datetime.datetime(2075, 10, 22, 5, 33, 24, 786222)
        dt = core.datetime.date(2075, 10, 22)
        self.assertEquals(core.datetime.date(2075, 11, 7),
                          (dt + datetimedelta(days=14)))
        self.assertEquals(core.datetime.date(2075, 11, 7),
                          (dt - datetimedelta(days=-14)))

        dt = core.datetime.date(2075, 10, 11)
        self.assertEquals(core.datetime.date(2075, 9, 27),
                          (dt - datetimedelta(days=14)))
        self.assertEquals(core.datetime.date(2075, 9, 27),
                          (dt + datetimedelta(days=-14)))

    def test_add_sub_mixed(self):
        dt = core.datetime.datetime(2075, 10, 22, 5, 33, 24, 786222)
        self.assertEquals(
            core.datetime.datetime(2075, 12, 6, 5, 33, 24, 786222),
            (dt + datetimedelta(months=1, days=14)))
        self.assertEquals(
            core.datetime.datetime(2076, 2, 28, 13, 35, 48, 786222),
            (dt + 4 * datetimedelta(months=1, days=1, hours=14, seconds=36)))
        self.assertEquals(
            core.datetime.datetime(2075, 10, 22, 5, 33, 24, 786222),
            (dt + datetimedelta(days=-1, hours=24)))
        self.assertEquals(
            core.datetime.datetime(2076, 2, 20, 13, 35, 48, 786222),
            (dt + 4 * datetimedelta(months=1, days=-1, hours=14, seconds=36)))

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

        dt_at_day = core.datetime.date(2076, 3, 11)
        self.assertTrue(dt > dt_at_day)
        self.assertTrue(dt >= dt_at_day)
        self.assertFalse(dt < dt_at_day)
        self.assertFalse(dt == dt_at_day)
        self.assertFalse(dt <= dt_at_day)

        dt_after = core.datetime.date(2076, 3, 12)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertFalse(dt > dt_after)
        self.assertFalse(dt == dt_after)
        self.assertFalse(dt >= dt_after)

        dt_after = core.datetime.date(2077, 3, 11)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertFalse(dt > dt_after)
        self.assertFalse(dt == dt_after)
        self.assertFalse(dt >= dt_after)

        dt_after = core.datetime.date(2076, 4, 11)
        self.assertTrue(dt < dt_after)
        self.assertTrue(dt <= dt_after)
        self.assertFalse(dt > dt_after)
        self.assertFalse(dt == dt_after)
        self.assertFalse(dt >= dt_after)

    def test_min_max_date(self):
        self.assertEqual(core.datetime.datetime.min,
                         core.datetime.datetime.from_ad_datetime(py_datetime(1, 1, 1)))
        self.assertEqual(core.datetime.datetime.max, core.datetime.datetime.from_ad_datetime(
            py_datetime(9999, 12, 31, 23, 59, 59, 999999)))

    def test_diff(self):
        ne_dt_1 = core.datetime.datetime(2075, 12, 7)
        ne_dt_2 = core.datetime.datetime(2075, 12, 8)
        self.assertEqual(ne_dt_2 - ne_dt_1, datetimedelta(days=1))

        ne_dt_1 = core.datetime.datetime(2075, 12, 7, 11, 5, 34, 999999)
        ne_dt_2 = core.datetime.datetime(2076, 1, 7, 11, 7, 34, 999999)
        self.assertEqual(ne_dt_2 - ne_dt_1,
                         datetimedelta(days=30, minutes=2))
