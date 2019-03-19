import sys
from datetime import date

core = sys.modules["core"]
"""
Standard Gregorian calendar date, wrapped with openIMIS data handling helpers
"""
class AdDate(date):
    def displayshortformat(self):
        return self.strftime(core.shortstrfdate)
    def displaylongformat(self):
        return self.strftime(core.longstrfdate)
    pass
