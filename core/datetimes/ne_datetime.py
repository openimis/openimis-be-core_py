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
    start_date = NepDate(values.START_NP_YEAR, 1 , 1)
    days = date - start_date
    return values.START_EN_DATE + days
date.to_ad_date = to_ad_date

def from_db_date(cls, value):
    if value is None:
        return None
    ad_dt = py_datetime.date(value.year, value.month, value.day)
    dt = date.from_ad_date(ad_dt)
    dt.update()
    return dt
date.from_db_date = classmethod(from_db_date)

def to_db_date(self):
    return self.to_ad_date()  
date.to_db_date = to_db_date