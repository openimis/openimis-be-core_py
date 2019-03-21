from nepalicalendar import NepDate

"""
Nepali calendar date (from https://github.com/nepalicalendar/nepalicalendar-py),
wrapped with openIMIS data handling helpers
"""

def isoformat(self):
    return "{0:04d}-{1:02d}-{2:02d}".format(self.year, self.month, self.day)
NepDate.isoformat = isoformat

def displayshortformat(self):
    return "%s/%s/%s" % (self.ne_day, self.ne_month, self.ne_year)
NepDate.displayshortformat = displayshortformat

def displaylongformat(self):
    return "%s %s %s %s" % (self.weekday_name(), self.ne_day, self.month_name(), self.ne_year)
NepDate.displaylongformat = displaylongformat