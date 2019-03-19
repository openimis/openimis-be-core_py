from nepalicalendar import NepCal
from nepalicalendar import values
from ..dates.ne_date import NepDate
from datetime import timedelta

"""
Nepali calendar (from https://github.com/nepalicalendar/nepalicalendar-py),
wrapped with openIMIS data handling helpers
"""
def weekday(year, month, day):
    return NepCal.weekday(year, month, day)

def monthrange(year, month):
    return (NepCal.weekday(year, month, 1), NepCal.monthrange(year,month))

def weekfirstday(dt: NepDate):
    dt.update()
    return (dt - timedelta(days=dt.weekday())).update()

def weeklastday(dt: NepDate):
    dt.update()
    return (dt + timedelta(days=(6-dt.weekday()))).update()

def monthfirstday(year, month):
    return NepDate(year, month, 1).update()

def monthlastday(year, month):
    return NepDate(year, month, monthrange(year, month)[1]).update()

def yearfirstday(year):
    return NepDate(year, 1, 1).update()

def yearlastday(year):
    return (yearfirstday(year) + timedelta(days=yeardayscount(year)-1)).update()

def monthdayscount(year: int, month: int):
    return monthrange(year, month)[1]

def yeardayscount(year: int):
    return sum(values.NEPALI_MONTH_DAY_DATA[year])

class Calendar(NepCal):
    pass

