import sys
from datetime import timedelta as py_timedelta
from datetime import tzinfo as py_tzinfo
from datetime import timezone as py_timezone
from datetime import date as py_date
from datetime import datetime as py_datetime
from .shared import datedelta

"""
Standard Gregorian date,
wrapped with openIMIS data handling helpers
"""

core = sys.modules["core"]

timedelta = py_timedelta
tzinfo = py_tzinfo
timezone = py_timezone


class AdDate(py_date):
    @classmethod
    def from_ad_date(cls, value):
        return AdDate(value.year, value.month, value.day)

    def to_ad_date(self):
        return self

    @classmethod
    def from_ad_datetime(cls, value):
        return AdDate(value.year, value.month, value.day)

    def to_ad_datetime(self):
        return AdDatetime(self.year, self.month, self.day)

    def raw_isoformat(self):
        return self.isoformat()

    def ad_isoformat(self):
        return self.isoformat()

    def displayshortformat(self):
        return self.strftime(core.shortstrfdate)

    def displaylongformat(self):
        return self.strftime(core.longstrfdate)

    def __add__(self, other):
        if isinstance(other, datedelta):
            return datedelta.add_to_date(other, self)
        dt = super(AdDate, self).__add__(other)
        return AdDate(dt.year, dt.month, dt.day)

    def __sub__(self, other):
        if isinstance(other, datedelta):
            return datedelta.add_to_date((other * -1), self)
        dt = super(AdDate, self).__sub__(other)
        return AdDate(dt.year, dt.month, dt.day)

    def __repr__(self):
        L = [self.year, self.month, self.day]
        if L[-1] == 0:
            del L[-1]
        if L[-1] == 0:
            del L[-1]
        return "%s.date(%s)" % (self.__class__.__module__,
                                ", ".join(map(str, L)))


date = AdDate


class AdDatetime(py_datetime):
    @classmethod
    def from_ad_date(cls, value):
        return AdDatetime(value.year, value.month, value.day)

    def to_ad_date(self):
        return AdDate(self.year, self.month, self.day)

    @classmethod
    def from_ad_datetime(cls, value):
        return AdDatetime(value.year, value.month, value.day,
                          value.hour, value.minute, value.second, value.microsecond,
                          value.tzinfo)

    def to_ad_datetime(self):
        return self

    def __add__(self, other):
        if isinstance(other, datedelta):
            return datedelta.add_to_date(other, self)
        dt = super(AdDatetime, self).__add__(other)
        return AdDatetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond, dt.tzinfo)

    def __sub__(self, other):
        if isinstance(other, datedelta):
            return datedelta.add_to_date((other * -1), self)
        dt = super(AdDatetime, self).__sub__(other)
        return AdDatetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond, dt.tzinfo)
       

    def __repr__(self):
        L = [self.year, self.month, self.day,
             self.hour, self.minute, self.second, self.microsecond]
        if L[-1] == 0:
            del L[-1]
        if L[-1] == 0:
            del L[-1]
        s = "%s.datetime(%s)" % (self.__class__.__module__,
                                 ", ".join(map(str, L)))
        if self.tzinfo is not None:
            assert s[-1:] == ")"
            s = s[:-1] + ", tzinfo=%r" % self.tzinfo + ")"
        if self.fold:
            assert s[-1:] == ")"
            s = s[:-1] + ", fold=1)"
        return s


datetime = AdDatetime
