import sys
from nepalicalendar import NepDate
from nepalicalendar import values
import datetime as py_datetime

"""
Nepali date (from https://github.com/nepalicalendar/nepalicalendar-py),
wrapped with openIMIS data handling helpers
"""

core = sys.modules["core"]

timedelta = py_datetime.timedelta
tzinfo = py_datetime.tzinfo
timezone = py_datetime.timezone
date = NepDate


def raw_isoformat(self):
    return "{0:04d}-{1:02d}-{2:02d}".format(self.year, self.month, self.day)


date.raw_isoformat = raw_isoformat


def ad_isoformat(self):
    dt = self.to_ad_date()
    return "{0:04d}-{1:02d}-{2:02d}".format(dt.year, dt.month, dt.day)


date.ad_isoformat = ad_isoformat


def isoformat(self):
    if core.iso_raw_date:
        return self.raw_isoformat()
    else:
        return self.ad_isoformat()


date.isoformat = isoformat


def displayshortformat(self):
    return "%s/%s/%s" % (self.ne_day, self.ne_month, self.ne_year)


date.displayshortformat = displayshortformat


def displaylongformat(self):
    return "%s %s %s %s" % (self.weekday_name(), self.ne_day, self.month_name(), self.ne_year)


date.displaylongformat = displaylongformat


def to_ad_date(date):
    start_date = NepDate(values.START_NP_YEAR, 1, 1)
    days = date - start_date
    ad_dt = values.START_EN_DATE + days
    return py_datetime.date(ad_dt.year, ad_dt.month, ad_dt.day)


date.to_ad_date = to_ad_date


def to_ad_datetime(date):
    start_date = NepDate(values.START_NP_YEAR, 1, 1)
    days = date - start_date
    ad_date = values.START_EN_DATE + days
    return py_datetime.datetime(ad_date.year, ad_date.month, ad_date.day)


date.to_ad_datetime = to_ad_datetime


def from_ad_datetime(cls, value):
    if value is None:
        return None
    ad_dt = py_datetime.date(value.year, value.month, value.day)
    dt = date.from_ad_date(ad_dt)
    dt.update()
    return dt


date.from_ad_datetime = classmethod(from_ad_datetime)

date.from_db_date = date.from_ad_date
date.from_db_datetime = date.from_ad_date


def to_db_date(self):
    return self.to_ad_date()


date.to_db_date = to_db_date


def to_db_datetime(self):
    return self.to_ad_datetime()


date.to_db_datetime = to_db_datetime


class NepDatetime(object):
    def __init__(self, year, month, day, hour=0, minute=0, second=0, microsecond=0, tzinfo=None, *, fold=0):
        self._date = date(year, month, day).update()
        self._time = py_datetime.time(
            hour, minute, second, microsecond, tzinfo)
        self._fold = fold

    @classmethod
    def from_ad_datetime(cls, datetime):
        ne_date = NepDate.from_ad_date(py_datetime.date(
            datetime.year, datetime.month, datetime.day))
        return NepDatetime(ne_date.year, ne_date.month, ne_date.day,
                           datetime.hour, datetime.minute, datetime.second, datetime.microsecond,
                           datetime.tzinfo)

    def to_ad_datetime(self):
        start_date = NepDate(values.START_NP_YEAR, 1, 1)
        days = self._date - start_date
        ad_dt = values.START_EN_DATE + days
        return py_datetime.datetime(ad_dt.year, ad_dt.month, ad_dt.day,
                           self._time.hour, self._time.minute, self._time.second, self._time.microsecond,
                           self._time.tzinfo)

    @classmethod
    def from_ad_date(cls, date):
        ne_date = NepDate.from_ad_date(py_datetime.date(
            date.year, date.month, date.day))
        return NepDatetime(ne_date.year, ne_date.month, ne_date.day)

    def to_ad_date(date):
        start_date = NepDate(values.START_NP_YEAR, 1, 1)
        days = date.date() - start_date
        ad_dt = values.START_EN_DATE + days
        return py_datetime.date(ad_dt.year, ad_dt.month, ad_dt.day)

    def date(self):
        return self._date

    def __eq__(self, other):
        return self._date == other._date and self._time == other._time and self._fold == other._fold

    def __repr__(self):
        return "NepDatetime(%d, %d, %d, %d, %d, %d, %d, %s, %d)" % (
            self._date.year, self._date.month, self._date.day,
            self._time.hour, self._time.minute, self._time.second, self._time.microsecond,
            self._time.tzinfo, self._fold
        )


datetime = NepDatetime
