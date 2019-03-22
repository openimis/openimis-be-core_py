import sys
from datetime import timedelta as py_timedelta
from datetime import tzinfo as py_tzinfo
from datetime import timezone as py_timezone
from datetime import date as py_date
from datetime import datetime as py_datetime

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

    @classmethod
    def from_db_date(cls, value):
        if value is None:
            return None
        return AdDate(value.year, value.month, value.day)

    def to_db_date(self):
        return self

    @classmethod
    def from_db_datetime(cls, value):
        if value is None:
            return None
        return AdDate(value.year, value.month, value.day)

    def to_db_datetime(self):
        return py_datetime(self.year, self.month, self.day)

    def raw_isoformat(self):
        return self.isoformat()

    def ad_isoformat(self):
        return self.isoformat()

    def displayshortformat(self):
        return self.strftime(core.shortstrfdate)

    def displaylongformat(self):
        return self.strftime(core.longstrfdate)

    def __add__(self, other):
        dt = super(AdDate, self).__add__(other)
        return AdDate(dt.year, dt.month, dt.day)

    def __sub__(self, other):
        dt = super(AdDate, self).__sub__(other)
        return AdDate(dt.year, dt.month, dt.day)


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

    @classmethod
    def from_db_date(cls, value):
        if value is None:
            return None
        return AdDatetime(value.year, value.month, value.day)

    def to_db_date(self):
        return py_date(self.year, self.month, self.day)

    @classmethod
    def from_db_datetime(cls, value):
        if value is None:
            return None
        return AdDatetime(value.year, value.month, value.day,
                          value.hour, value.minute, value.second, value.microsecond,
                          value.tzinfo)

    def to_db_datetime(self):
        return self


datetime = AdDatetime
