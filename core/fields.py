from django.db import models
import datetime as py_datetime


class DateField(models.DateField):
    description = "Calendar-aware Date field"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        from core import datetime
        return datetime.date.from_ad_date(py_datetime.date(value.year, value.month, value.day))

    def get_prep_value(self, value):
        if hasattr(value, 'to_ad_date'):
            value = value.to_ad_date()
        return models.DateTimeField().get_prep_value(value)


class DateTimeField(models.DateTimeField):
    description = "Calendar-aware DateTime field"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        from core import datetime
        return datetime.datetime.from_ad_datetime(value)

    def get_prep_value(self, value):
        if hasattr(value, 'to_ad_datetime'):
            value = value.to_ad_datetime()
        return models.DateTimeField().get_prep_value(value)
