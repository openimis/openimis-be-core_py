import sys
from django.db import models
import datetime as py_datetime

class DateField(models.DateField):
    description = "Calendar-aware Date field"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        from core import datetime
        return datetime.date.from_db_date(value)

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        return value.to_ad_date()
    pass