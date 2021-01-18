import sys
import datetime as py_datetime
from .shared import datetimedelta

__all__ = ["tzinfo", "timezone", "AdDate", "date", "AdDatetime", "datetime"]

"""
Standard Gregorian date,
wrapped with openIMIS data handling helpers
"""

core = sys.modules["core"]

tzinfo = py_datetime.tzinfo
timezone = py_datetime.timezone


class AdDate(py_datetime.date):

    @classmethod
    def today(cls):
        return AdDate.from_ad_date(py_datetime.date.today())

    @classmethod
    def from_ad_date(cls, value):
        if value is None:
            return None
        return AdDate(value.year, value.month, value.day)

    def to_ad_date(self):
        return self

    @classmethod
    def from_ad_datetime(cls, value):
        return AdDate.from_ad_date(value)

    def to_ad_datetime(self):
        return AdDatetime(self.year, self.month, self.day)

    def to_datetime(self):
        return self.to_ad_datetime()

    def raw_isoformat(self):
        return self.isoformat()

    def ad_isoformat(self):
        return self.isoformat()

    def displayshortformat(self):
        return self.strftime(core.shortstrfdate)

    def displaylongformat(self):
        return self.strftime(core.longstrfdate)

    @classmethod
    def _convert_op_res(cls, res):
        if isinstance(res, py_datetime.datetime):
            return AdDate.from_ad_datetime(res)
        if isinstance(res, py_datetime.date):
            return AdDate.from_ad_date(res)
        return res

    def __add__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta.add_to_date(other, self)
        dt = super(AdDate, self).__add__(other)
        return AdDate._convert_op_res(dt)

    def __sub__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta.add_to_date((other * -1), self)
        dt = super(AdDate, self).__sub__(other)
        return AdDate._convert_op_res(dt)

    def __repr__(self):
        L = [self.year, self.month, self.day]
        if L[-1] == 0:
            del L[-1]
        if L[-1] == 0:
            del L[-1]
        return "%s.date(%s)" % (self.__class__.__module__,
                                ", ".join(map(str, L)))


date = AdDate
date.min = AdDate(1, 1, 1)
date.max = AdDate(9999, 12, 31)


class AdDatetime(py_datetime.datetime):

    @classmethod
    def now(cls):
        return cls.from_ad_datetime(py_datetime.datetime.now())

    @classmethod
    def from_ad_date(cls, value):
        if value is None:
            return None
        return AdDatetime(value.year, value.month, value.day)

    def to_ad_date(self):
        return AdDate(self.year, self.month, self.day)

    @classmethod
    def from_ad_datetime(cls, value):
        if value is None:
            return None
        return AdDatetime(value.year, value.month, value.day,
                          value.hour, value.minute, value.second, value.microsecond,
                          value.tzinfo)

    def to_ad_datetime(self):
        return self

    def __eq__(self, other):
        if other is None:
            return super(AdDatetime, self).__eq__(other)
        if isinstance(other, py_datetime.datetime):
            return super(AdDatetime, self).__eq__(other)
        if isinstance(other, py_datetime.date):
            return super(AdDatetime, self).__eq__(AdDatetime.from_ad_date(other))
        return self - other == datetimedelta()

    @classmethod
    def _convert_op_res(cls, res):
        if isinstance(res, py_datetime.datetime):
            return AdDatetime.from_ad_datetime(res)
        return res

    def __add__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta.add_to_date(other, self)
        dt = super(AdDatetime, self).__add__(other)
        return AdDatetime._convert_op_res(dt)

    def __sub__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta.add_to_date((other * -1), self)
        dt = super(AdDatetime, self).__sub__(other)
        return AdDatetime._convert_op_res(dt)

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
