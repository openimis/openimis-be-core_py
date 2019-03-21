from django.test import TestCase
from datetime import date as py_date
from .ne_datetime import date


class DateTestCase(TestCase):
    def test_from_ad_date(self):
        ad_dt = py_date(2020, 1, 13)
        ne_dt = date.from_ad_date(ad_dt)
        self.assertEqual(ne_dt, date(2076, 9, 28))
        looped_dt = ne_dt.to_ad_date()
        self.assertEqual(ad_dt, looped_dt)    
