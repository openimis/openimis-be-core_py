import sys
from nepalicalendar import NepDate
from nepalicalendar import values
import datetime as py_datetime
from .shared import datetimedelta

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
    def from_ad_date(cls, dt):
        if isinstance(dt, py_datetime.datetime):
            dt = py_datetime.date(dt.year, dt.month, dt.day)
        if dt is None:
            return None
        if dt < values.START_EN_DATE:
            return date.min
        if dt > values.END_EN_DATE:
            return date.max
        ne_dte = NepDate.from_ad_date(dt)
        return NeDate(ne_dte.year, ne_dte.month, ne_dte.day).update()

    @classmethod
    def from_ad_datetime(cls, value):
        if value is None:
            return None
        ad_dt = py_datetime.date(value.year, value.month, value.day)
        return date.from_ad_date(ad_dt)

    @classmethod
    def today(cls):
        nep_today = NepDate.today()
        return NeDate(nep_today.year, nep_today.month, nep_today.day).update()

    def __add__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta.add_to_date(other, self)
        dt = super(NeDate, self).__add__(other)
        if isinstance(dt, NepDate):
            return NeDate(dt.year, dt.month, dt.day).update()
        return dt

    def __sub__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta.add_to_date(-other, self)
        dt = super(NeDate, self).__sub__(other)
        if isinstance(dt, NepDate):
            return NeDate(dt.year, dt.month, dt.day).update()
        return dt

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
date.min = NeDate.from_ad_date(values.START_EN_DATE)
date.max = NeDate.from_ad_date(values.END_EN_DATE)
date.min_ad = values.START_EN_DATE
date.max_ad = values.END_EN_DATE
date.resolution = timedelta(days=1)


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

    @property
    def fold(self):
        return self._fold

    def isoformat(self, *args, **kwargs):
        return "%s %s" % (self._date.isoformat(), self._time.isoformat(*args, **kwargs))

    @classmethod
    def from_ad_datetime(cls, dt):
        if dt < py_datetime.datetime(date.min_ad.year, date.min_ad.month, date.min_ad.day, tzinfo= dt.tzinfo):
            return datetime.min
        if dt > py_datetime.datetime(date.max_ad.year, date.max_ad.month, date.max_ad.day, 23, 59, 59, 999999, tzinfo= dt.tzinfo):
            return datetime.max
        ne_dte = NeDate.from_ad_date(py_datetime.date(
            dt.year, dt.month, dt.day))
        return NeDatetime(ne_dte.year, ne_dte.month, ne_dte.day,
                          dt.hour, dt.minute, dt.second, dt.microsecond,
                          dt.tzinfo)

    def to_ad_datetime(self):
        start_date = NeDate(values.START_NP_YEAR, 1, 1)
        days = self._date - start_date
        ad_dt = values.START_EN_DATE + days
        return py_datetime.datetime(ad_dt.year, ad_dt.month, ad_dt.day,
                                    self._time.hour, self._time.minute, self._time.second, self._time.microsecond,
                                    self._time.tzinfo)

    @classmethod
    def from_ad_date(cls, dt):
        if isinstance(dt, py_datetime.date):
            dt = py_datetime.datetime(dt.year, dt.month, dt.day)
        if dt < py_datetime.datetime(date.min_ad.year, date.min_ad.month, date.min_ad.day, tzinfo= dt.tzinfo):
            return datetime.min
        if dt > py_datetime.datetime(date.max_ad.year, date.max_ad.month, date.max_ad.day, 23, 59, 59, 999999, tzinfo= dt.tzinfo):
            return datetime.max
        ne_dte = NeDate.from_ad_date(py_datetime.date(
            dt.year, dt.month, dt.day))
        return NeDatetime(ne_dte.year, ne_dte.month, ne_dte.day)

    def to_ad_date(self):
        start_date = NeDate(values.START_NP_YEAR, 1, 1)
        days = self.date() - start_date
        ad_dt = values.START_EN_DATE + days
        return py_datetime.date(ad_dt.year, ad_dt.month, ad_dt.day)

    def date(self):
        return self._date

    def __eq__(self, other):
        if isinstance(other, NeDatetime):
            return self._date == other._date and self._time == other._time and self.fold == other.fold
        if isinstance(other, NeDate):
            return self.year == other.year and self.month == other.month and self.day == other.day \
                and self.hour == 0 and self.minute == 0 and self.second == 0 and self.microsecond == 0 \
                and self.fold == 0
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, NeDatetime):
            if self._date > other._date:
                return True
            if self._date < other._date:
                return False
            return self._time > other._time
        if isinstance(other, NeDate):
            if self.year > other.year:
                return True
            if self.year < other.year:
                return False
            if self.month > other.month:
                return True
            if self.month < other.month:
                return False
            if self.day > other.day:
                return True
            if self.year < other.day:
                return False
            return self.hour > 0 or self.minute > 0 or self.second > 0 or self.microsecond > 0
        return NotImplemented

    def __lt__(self, other):
        return (not self == other) and (not self > other)

    def __ge__(self, other):
        return not self < other

    def __le__(self, other):
        return not self > other

    def __add__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta.add_to_datetime(other, self)
        if isinstance(other, NeDatetime):
            return NeDatetime.from_ad_datetime(self.to_ad_datetime().__add__(other.to_ad_datetime()))
        dt = self.to_ad_datetime().__add__(other)
        if isinstance(dt, py_datetime.datetime):
            return NeDatetime.from_ad_datetime(dt)
        return dt

    def __sub__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta.add_to_date(-other, self)
        if isinstance(other, NeDatetime):
            return self.to_ad_datetime().__sub__(other.to_ad_datetime())
        dt = self.to_ad_datetime().__sub__(other)
        if isinstance(dt, py_datetime.datetime):
            return NeDatetime.from_ad_datetime(dt)
        return dt

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
datetime.min = NeDatetime(date.min.year, date.min.month, date.min.day)
datetime.max = NeDatetime(date.max.year, date.max.month,
                          date.max.day, 23, 59, 59, 999999)
datetime.min_ad = py_datetime.datetime(
    date.min_ad.year, date.min_ad.month, date.min_ad.day)
datetime.max_ad = py_datetime.datetime(
    date.max_ad.year, date.max_ad.month, date.max_ad.day, 23, 59, 59, 999999)
