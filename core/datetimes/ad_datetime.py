import sys
from datetime import timedelta as py_timedelta
from datetime import tzinfo as py_tzinfo
from datetime import timezone as py_timezone
from datetime import date as py_date

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
    def from_db_date(cls, value):
        if value is None:
            return None
        return AdDate(value.year, value.month, value.day)

    def to_db_date(self):
        return self

    def raw_isoformat(self):
        return self.isoformat()

    def ad_isoformat(self):
        return self.isoformat()

    def displayshortformat(self):
        return self.strftime(core.shortstrfdate)

    def displaylongformat(self):
        return selfstrftime(core.longstrfdate)

    def __add__(self, other):
        dt = super(AdDate, self).__add__(other)
        return AdDate(dt.year, dt.month, dt.day)

    def __sub__(self, other):
        dt = super(AdDate, self).__sub__(other)
        return AdDate(dt.year, dt.month, dt.day)       

date = AdDate