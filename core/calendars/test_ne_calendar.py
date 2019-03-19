from django.test import TestCase
from datetime import date
from ..dates.ne_date import NepDate
from .ne_calendar import *


class CalendarTestCase(TestCase):
    def test_from_ad_date(self):
        dt = NepDate.from_ad_date(date(2020, 1, 13))
        self.assertEqual(dt, NepDate(2076, 9, 28))

    def test_weekfirstday(self):
        dt = NepDate(2076, 9, 28)
        fwd = weekfirstday(dt)
        self.assertEqual(fwd, NepDate(2076, 9, 27))

    def test_weeklastday(self):
        dt = NepDate(2076, 9, 28)
        fwd = weeklastday(dt)
        self.assertEqual(fwd, NepDate(2076, 10, 4))

    def test_monthfirstday(self):
        dt = monthfirstday(2076, 9)
        self.assertEqual(dt, NepDate(2076, 9, 1))

    def test_monthlastday(self):
        dt = monthlastday(2019, 2)
        self.assertEqual(dt, NepDate(2019, 2, 32))

    def test_yearfirstday(self):
        dt = yearfirstday(2075)
        self.assertEqual(dt, NepDate(2075, 1, 1))

    def test_yearlastday(self):
        dt = yearlastday(2075)
        self.assertEqual(dt, NepDate(2075, 12, 30))

    def test_monthdayscount(self):
        self.assertEqual(32, monthdayscount(2019, 2))
        self.assertEqual(29, monthdayscount(2075, 10))              

    def test_yeardayscount(self):
        self.assertEqual(365, yeardayscount(2076))
        self.assertEqual(366, yeardayscount(2077))        
