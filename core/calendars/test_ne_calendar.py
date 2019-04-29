import sys
import importlib
import core
from django.test import TestCase
from datetime import date as py_date


class CalendarTestCase(TestCase):
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

    def test_from_ad_date(self):
        dt = core.datetime.date.from_ad_date(py_date(2020, 1, 13))
        self.assertEqual(dt, core.datetime.date(2076, 9, 28))

    def test_weekfirstday(self):
        dt = core.datetime.date(2076, 9, 28)
        fwd = core.calendar.weekfirstday(dt)
        self.assertEqual(fwd, core.datetime.date(2076, 9, 27))

    def test_weeklastday(self):
        dt = core.datetime.date(2076, 9, 28)
        fwd = core.calendar.weeklastday(dt)
        self.assertEqual(fwd, core.datetime.date(2076, 10, 4))

    def test_weekday(self):
        wd = core.calendar.weekday(2076, 9, 11)
        self.assertEqual(wd, 5)
        wd = core.calendar.weekday(2076, 9, 28)
        self.assertEqual(wd, 1)        

    def test_monthfirstday(self):
        dt = core.calendar.monthfirstday(2076, 9)
        self.assertEqual(dt, core.datetime.date(2076, 9, 1))

    def test_monthlastday(self):
        dt = core.calendar.monthlastday(2019, 2)
        self.assertEqual(dt, core.datetime.date(2019, 2, 32))

    def test_yearfirstday(self):
        dt = core.calendar.yearfirstday(2075)
        self.assertEqual(dt, core.datetime.date(2075, 1, 1))

    def test_yearlastday(self):
        dt = core.calendar.yearlastday(2075)
        self.assertEqual(dt, core.datetime.date(2075, 12, 30))

    def test_monthdayscount(self):
        self.assertEqual(32, core.calendar.monthdayscount(2019, 2))
        self.assertEqual(29, core.calendar.monthdayscount(2075, 10))

    def test_yeardayscount(self):
        self.assertEqual(365, core.calendar.yeardayscount(2076))
        self.assertEqual(366, core.calendar.yeardayscount(2077))
