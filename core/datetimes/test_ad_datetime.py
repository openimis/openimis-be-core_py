from django.test import TestCase
from datetime import date as py_date
from datetime import datetime as py_datetime
from .ad_datetime import date, datetime, timedelta


class DateTestCase(TestCase):
    def test_ad_date(self):
        py_dt = py_date(2020, 1, 13)
        ad_dt = date(2020, 1, 13)
        self.assertEqual(py_dt, ad_dt)

    def test_from_db_date(self):
        db_dt = date.from_db_date(py_date(2020, 1, 13))
        ad_dt = date(2020, 1, 13)
        self.assertEqual(db_dt, ad_dt)

    def test_from_db_datetime(self):
        db_dt = date.from_db_datetime(py_datetime(2020, 1, 13))
        ad_dt = date(2020, 1, 13)
        self.assertEqual(db_dt, ad_dt)

    def test_to_db_date(self):
        ad_dt = date(2020, 1, 13)
        db_dt = ad_dt.to_db_date()
        self.assertEqual(db_dt, ad_dt)

    def test_to_db_datetime(self):
        ad_dt = date(2020, 1, 13)
        db_dt = ad_dt.to_db_datetime()
        self.assertEqual(db_dt, py_datetime(2020, 1, 13))

    def test_raw_iso_format(self):
        dt = date(2019, 3, 22)
        self.assertEquals("2019-03-22", dt.raw_isoformat())

    def test_ad_iso_format(self):
        dt = date(2019, 3, 22)
        self.assertEquals("2019-03-22", dt.ad_isoformat())

    def test_add_days(self):
        dt = date(2019, 3, 22)
        dt_plus = dt + timedelta(days=14)
        self.assertEquals(date(2019, 4, 5), dt_plus)


class DatetimeTestCase(TestCase):
    def test_ad_datetime(self):
        py_dt = py_datetime(2020, 1, 13, 10, 9, 55, 728267)
        ad_dt = datetime(2020, 1, 13, 10, 9, 55, 728267)
        self.assertEqual(py_dt, ad_dt)

    def test_from_db_date(self):
        db_dt = date.from_db_date(py_date(2020, 1, 13))
        ad_dt = datetime(2020, 1, 13)
        self.assertEqual(db_dt, ad_dt)

    def test_from_db_datetime(self):
        db_dt = datetime.from_db_datetime(
            py_datetime(2020, 1, 13, 11, 22, 33, 444555))
        ne_dt = datetime(2020, 1, 13, 11, 22, 33, 444555)
        self.assertEqual(db_dt, ne_dt)

    def test_to_db_date(self):
        ne_dt = datetime(2020, 1, 13, 11, 22, 33, 444555)
        db_dt = ne_dt.to_db_date()
        py_dt = py_date(2020, 1, 13)
        self.assertEqual(db_dt, py_dt)

    def test_to_db_datetime(self):
        ne_dt = datetime(2020, 1, 13, 11, 22, 33, 444555)
        db_dt = ne_dt.to_db_datetime()
        py_dt = py_datetime(2020, 1, 13, 11, 22, 33, 444555)
        self.assertEqual(db_dt, py_dt)
