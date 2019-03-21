from django.test import TestCase
from ..datetimes.ad_datetime import date
from .ad_calendar import *


class CalendarTestCase(TestCase):
    def test_weekfirstday(self):
        dte = date(2019, 3, 19)
        fwd = weekfirstday(dte)
        self.assertEqual(fwd, date(2019, 3, 18))

    def test_weeklastday(self):
        dte = date(2019, 3, 19)
        fwd = weeklastday(dte)
        self.assertEqual(fwd, date(2019, 3, 24))

    def test_monthfirstday(self):
        dte = monthfirstday(2019, 3)
        self.assertEqual(dte, date(2019, 3, 1))

    def test_monthlastday(self):
        dte = monthlastday(2019, 3)
        self.assertEqual(dte, date(2019, 3, 31))

    def test_yearfirstday(self):
        dte = yearfirstday(2019)
        self.assertEqual(dte, date(2019, 1, 1))

    def test_yearlastday(self):
        dte = yearlastday(2019)
        self.assertEqual(dte, date(2019, 12, 31))

    def test_monthdayscount(self):
        self.assertEqual(29, monthdayscount(2020, 2))
        self.assertEqual(31, monthdayscount(2019, 12))          

    def test_yeardayscount(self):
        self.assertEqual(365, yeardayscount(2019))
        self.assertEqual(366, yeardayscount(2020))
