import calendar
from ..datetimes.ad_datetime import *

"""
Standard Gregorian calendar,
wrapped with openIMIS data handling helpers
"""

for k,v in vars(calendar).items():
    if callable(v):
        globals()[k] = v

def weekfirstday(dt: date):
    return dt - timedelta(days=dt.weekday())

def weeklastday(dt: date):
    return dt + timedelta(days=(6-dt.weekday()))

def monthfirstday(year: int, month: int):    
    return date(year, month, 1)

def monthlastday(year: int, month: int):
    return date(year, month, monthrange(year, month)[1])

def yearfirstday(year: int):
    return date(year, 1, 1)

def yearlastday(year: int):
    return date(year, 12, 31)   

def monthdayscount(year: int, month: int):
    return monthrange(year, month)[1]

def yearmonthscount(year: int):
    return 12
    
def yeardayscount(year: int):
    return 366 if isleap(year) else 365
