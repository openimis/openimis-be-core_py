import sys
import importlib
import core
from django.test import TestCase
from ..datetimes.ad_datetime import date
from .ad_calendar import *


class CalendarTestCase(TestCase):
    def setUp(self):
        core.calendar = importlib.import_module(
            '.calendars.ad_calendar', 'core')
        core.datetime = importlib.import_module(
            '.datetimes.ad_datetime', 'core')

    def test_weekfirstday(self):
        dte = core.datetime.date(2019, 3, 19)
        fwd = core.calendar.weekfirstday(dte)
        self.assertEqual(fwd, core.datetime.date(2019, 3, 18))

    def test_weeklastday(self):
        dte = core.datetime.date(2019, 3, 19)
        fwd = core.calendar.weeklastday(dte)
        self.assertEqual(fwd, core.datetime.date(2019, 3, 24))

    def test_monthfirstday(self):
        dte = core.calendar.monthfirstday(2019, 3)
        self.assertEqual(dte, core.datetime.date(2019, 3, 1))

    def test_monthlastday(self):
        dte = core.calendar.monthlastday(2019, 3)
        self.assertEqual(dte, core.datetime.date(2019, 3, 31))

    def test_yearfirstday(self):
        dte = core.calendar.yearfirstday(2019)
        self.assertEqual(dte, core.datetime.date(2019, 1, 1))

    def test_yearlastday(self):
        dte = core.calendar.yearlastday(2019)
        self.assertEqual(dte, core.datetime.date(2019, 12, 31))

    def test_monthdayscount(self):
        self.assertEqual(29, core.calendar.monthdayscount(2020, 2))
        self.assertEqual(31, core.calendar.monthdayscount(2019, 12))

    def test_yeardayscount(self):
        self.assertEqual(365, core.calendar.yeardayscount(2019))
        self.assertEqual(366, core.calendar.yeardayscount(2020))
