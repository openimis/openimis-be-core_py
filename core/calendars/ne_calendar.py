from nepalicalendar import NepCal
from nepalicalendar import values
from ..datetimes.ne_datetime import date
from ..datetimes.shared import datetimedelta

"""
Nepali calendar (from https://github.com/nepalicalendar/nepalicalendar-py),
wrapped with openIMIS data handling helpers
"""

def weekday(year, month, day):
    return NepCal.weekday(year, month, day)

def monthrange(year, month):
    return (NepCal.weekday(year, month, 1), NepCal.monthrange(year,month))

def weekfirstday(dt: date):
    dt.update()
    return (dt - datetimedelta(days=dt.weekday())).update()

def weeklastday(dt: date):
    dt.update()
    return (dt + datetimedelta(days=(6-dt.weekday()))).update()

def monthfirstday(year, month):
    return date(year, month, 1).update()

def monthlastday(year, month):
    return date(year, month, monthrange(year, month)[1]).update()

def yearfirstday(year):
    return date(year, 1, 1).update()

def yearlastday(year):
    return (yearfirstday(year) + datetimedelta(days=yeardayscount(year)-1)).update()

def monthdayscount(year: int, month: int):
    return monthrange(year, month)[1]

def yearmonthscount(year: int):
    return 12

def yeardayscount(year: int):
    return sum(values.NEPALI_MONTH_DAY_DATA[year])

