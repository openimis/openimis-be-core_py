import sys
from nepalicalendar import NepDate
from nepalicalendar import values
import datetime as py_datetime
from .shared import datedelta

"""
Nepali date (from https://github.com/nepalicalendar/nepalicalendar-py),
wrapped with openIMIS data handling helpers
"""

core = sys.modules["core"]

timedelta = py_datetime.timedelta
tzinfo = py_datetime.tzinfo
timezone = py_datetime.timezone


class NeDate(NepDate):

    def raw_isoformat(self, *args, **kwargs):
        return "%04d-%02d-%02d" % (self.year, self.month, self.day)

    def ad_isoformat(self, *args, **kwargs):
        return self.to_ad_date().isoformat(*args, **kwargs)

    def isoformat(self):
        if core.iso_raw_date:
            return self.raw_isoformat()
        else:
            return self.ad_isoformat()

    def displayshortformat(self):
        return "%s/%s/%s" % (self.ne_day, self.ne_month, self.ne_year)

    def displaylongformat(self):
        return "%s %s %s %s" % (self.weekday_name(), self.ne_day, self.month_name(), self.ne_year)

    def to_ad_date(self):
        start_date = NeDate(values.START_NP_YEAR, 1, 1)
        days = self - start_date
        ad_dt = values.START_EN_DATE + days
        return py_datetime.date(ad_dt.year, ad_dt.month, ad_dt.day)

    def to_ad_datetime(self):
        start_date = NeDate(values.START_NP_YEAR, 1, 1)
        days = self - start_date
        ad_date = values.START_EN_DATE + days
        return py_datetime.datetime(ad_date.year, ad_date.month, ad_date.day)

    @classmethod
    def from_ad_date(cls, date):
        if date is None:
            return None        
        ne_dte = NepDate.from_ad_date(date)
        return NeDate(ne_dte.year, ne_dte.month, ne_dte.day)

    @classmethod
    def from_ad_datetime(cls, value):
        if value is None:
            return None
        ad_dt = py_datetime.date(value.year, value.month, value.day)
        dt = date.from_ad_date(ad_dt)
        dt.update()
        return dt

    def __add__(self, other):
        if isinstance(other, datedelta):
            return datedelta.add_to_date(other, self)
        return super(NeDate, self).__add__(other)

    def __sub__(self, other):
        if isinstance(other, datedelta):
            return datedelta.add_to_date(-other, self)   
        return super(NeDate, self).__sub__(other)

    def __repr__(self):
        L = [self.year, self.month, self.day]
        if L[-1] == 0:
            del L[-1]
        if L[-1] == 0:
            del L[-1]
        return "core.datetimes.ne_datetime.date(%s)" % (", ".join(map(str, L)))

    def __str__(self):
        return self.raw_isoformat()

date = NeDate

class NeDatetime(object):
    __slots__ = ['_date', '_time', '_fold']

    def __init__(self, year, month, day, hour=0, minute=0, second=0, microsecond=0, tzinfo=None, *, fold=0):
        self._date = date(year, month, day).update()
        self._time = py_datetime.time(
            hour, minute, second, microsecond, tzinfo)
        self._fold = fold

    @property
    def year(self):
        return self._date.year

    @property
    def month(self):
        return self._date.month

    @property
    def day(self):
        return self._date.day

    @property
    def hour(self):
        return self._time.hour

    @property
    def minute(self):
        return self._time.minute

    @property
    def second(self):
        return self._time.second

    @property
    def microsecond(self):
        return self._time.microsecond

    @property
    def tzinfo(self):
        return self._time.tzinfo

    def isoformat(self, *args, **kwargs):
        return "%s %s" % (self._date.isoformat(), self._time.isoformat(*args, **kwargs))

    @classmethod
    def from_ad_datetime(cls, datetime):
        ne_dte = NeDate.from_ad_date(py_datetime.date(
            datetime.year, datetime.month, datetime.day))
        return NeDatetime(ne_dte.year, ne_dte.month, ne_dte.day,
                           datetime.hour, datetime.minute, datetime.second, datetime.microsecond,
                           datetime.tzinfo)

    def to_ad_datetime(self):
        start_date = NeDate(values.START_NP_YEAR, 1, 1)
        days = self._date - start_date
        ad_dt = values.START_EN_DATE + days
        return py_datetime.datetime(ad_dt.year, ad_dt.month, ad_dt.day,
                                    self._time.hour, self._time.minute, self._time.second, self._time.microsecond,
                                    self._time.tzinfo)

    @classmethod
    def from_ad_date(cls, date):
        ne_dte = NeDate.from_ad_date(py_datetime.date(
            date.year, date.month, date.day))
        return NeDatetime(ne_dte.year, ne_dte.month, ne_dte.day)

    def to_ad_date(date):
        start_date = NeDate(values.START_NP_YEAR, 1, 1)
        days = date.date() - start_date
        ad_dt = values.START_EN_DATE + days
        return py_datetime.date(ad_dt.year, ad_dt.month, ad_dt.day)

    def date(self):
        return self._date

    def __eq__(self, other):
        return self._date == other._date and self._time == other._time and self._fold == other._fold

    def __gt__(self, other):
        if self._date > other._date:
            return True
        if self._date < other._date:
            return False
        return self._time > other._time

    def __lt__(self, other):
        return (not self == other) and (not self > other)

    def __ge__(self, other):
        return not self < other

    def __le__(self, other):
        return not self > other

    def __add__(self, other):
        if isinstance(other, datedelta):
            return datedelta.add_to_datetime(other, self)
        if isinstance(other, NeDatetime):
            return NeDatetime.from_ad_datetime(self.to_ad_datetime().__add__(other.to_ad_datetime))
        return NeDatetime.from_ad_datetime(self.to_ad_datetime().__add__(other))

    def __sub__(self, other):
        if isinstance(other, datedelta):
            return datedelta.add_to_date(-other, self)
        if isinstance(other, NeDatetime):
            return NeDatetime.from_ad_datetime(self.to_ad_datetime().__sub__(other.to_ad_datetime))
        return NeDatetime.from_ad_datetime(self.to_ad_datetime().__sub__(other))

    def __repr__(self):
        L = [self._date.year, self._date.month, self._date.day,
             self._time.hour, self._time.minute, self._time.second, self._time.microsecond]
        if L[-1] == 0:
            del L[-1]
        if L[-1] == 0:
            del L[-1]
        s = "%s.datetime(%s)" % (self.__class__.__module__,
                                 ", ".join(map(str, L)))
        if self._time.tzinfo is not None:
            assert s[-1:] == ")"
            s = s[:-1] + ", tzinfo=%r" % self.tzinfo + ")"
        if self._fold:
            assert s[-1:] == ")"
            s = s[:-1] + ", fold=1)"
        return s

    def __str__(self):
        s = "%s %s" % (self._date, self._time)
        if self._fold:
            assert s[-1:] == ")"
            s = s[:-1] + ", fold=1)"
        return s


datetime = NeDatetime
