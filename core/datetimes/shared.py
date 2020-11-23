from datetime import timedelta

__all__ = ["is_midnight", "datetimedelta"]


def _cmperror(x, y):
    raise TypeError("can't compare '%s' to '%s'" % (
                    type(x).__name__, type(y).__name__))


def is_midnight(dt):
    if hasattr(dt, 'hour') and dt.hour != 0:
        return False
    if hasattr(dt, 'minute') and dt.minute != 0:
        return False
    if hasattr(dt, 'second') and dt.second != 0:
        return False
    if hasattr(dt, 'microsecond') and dt.microsecond != 0:
        return False
    return True


def _cmp(x, y):
    return 0 if x == y else 1 if x > y else -1


def _add_month(dt):
    from core import calendar
    return dt + timedelta(calendar.monthdayscount(dt.year, dt.month))


def _sub_month(dt):
    from core import calendar
    if dt.month == 1:
        prev_year = dt.year - 1
        return dt - \
            timedelta(calendar.monthdayscount(
                prev_year, calendar.yearmonthscount(prev_year)))
    else:
        return dt - \
            timedelta(calendar.monthdayscount(
                dt.year, dt.month - 1))


class datetimedelta(object):
    __slots__ = ['_years', '_months', '_timedelta', '_hashcode']

    def __init__(self, years=0, months=0, weeks=0, days=0,
                 hours=0, minutes=0, seconds=0, microseconds=0):
        self._years = years
        self._months = months
        self._timedelta = timedelta(
            weeks=weeks, days=days,
            hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
        self._hashcode = -1

    @property
    def years(self):
        return self._years

    @property
    def months(self):
        return self._months

    @property
    def days(self):
        return self._timedelta.days

    @property
    def seconds(self):
        return self._timedelta.seconds

    @property
    def microseconds(self):
        return self._timedelta.microseconds

    @classmethod
    def from_timedelta(cls, td):
        return datetimedelta(years=0, months=0, days=td.days, seconds=td.seconds, microseconds=td.microseconds)

    def _add_years(self, dt):
        while True:  # there are many '29/02' in nepali calendar
            try:
                return dt.replace(year=dt.year + self._years)
            except ValueError:
                return (dt - datetimedelta(days=1)) + self

    def _add_months(self, dt):
        for i in range(abs(self._months)):
            if self._months > 0:
                dt = _add_month(dt)
            else:
                dt = _sub_month(dt)
        return dt

    def add_to_date(self, dt):
        dt = self._add_years(dt)
        dt = self._add_months(dt)
        return dt + self._timedelta

    def add_to_datetime(self, datetime):
        return self.add_to_date(datetime)

    def __add__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta(years=self.years + other.years,
                                 months=self.months + other.months,
                                 days=self.days + other.days,
                                 seconds=self.seconds + other.seconds,
                                 microseconds=self.microseconds + other.microseconds)
        return NotImplemented

    __radd__ = __add__

    def __sub__(self, other):
        if isinstance(other, datetimedelta):
            return datetimedelta(years=self.years - other.years,
                                 months=self.months - other.months,
                                 days=self.days - other.days,
                                 seconds=self.seconds - other.seconds,
                                 microseconds=self.microseconds - other.microseconds)
        return NotImplemented

    def __rsub__(self, other):
        if isinstance(other, datetimedelta):
            return -self + other
        return NotImplemented

    def __neg__(self):
        return datetimedelta(years=-self.years,
                             months=-self.months,
                             days=-self.days,
                             seconds=-self.seconds,
                             microseconds=-self.microseconds)

    def __pos__(self):
        return self

    def __abs__(self):
        if self.years < 0:
            return -self
        if self.years == 0 and self.months < 0:
            return -self
        if self.years == 0 and self.months == 0:
            td = abs(self._timedelta)
            return datetimedelta(years=0, months=0, days=td.days, seconds=td.seconds, microseconds=td.microseconds)
        return self

    def __mul__(self, other):
        if isinstance(other, int):
            return datetimedelta(years=self.years * other,
                                 months=self.months * other,
                                 days=self.days * other,
                                 seconds=self.seconds * other,
                                 microseconds=self.microseconds * other)
        return NotImplemented

    __rmul__ = __mul__

    def __eq__(self, other):
        if isinstance(other, timedelta):
            return self._cmp(datetimedelta.from_timedelta(other)) == 0
        if isinstance(other, datetimedelta):
            return self._cmp(other) == 0
        else:
            _cmperror(self, other)

    def __le__(self, other):
        if isinstance(other, datetimedelta):
            return self._cmp(other) <= 0
        else:
            _cmperror(self, other)

    def __lt__(self, other):
        if isinstance(other, datetimedelta):
            return self._cmp(other) < 0
        else:
            _cmperror(self, other)

    def __ge__(self, other):
        if isinstance(other, datetimedelta):
            return self._cmp(other) >= 0
        else:
            _cmperror(self, other)

    def __gt__(self, other):
        if isinstance(other, datetimedelta):
            return self._cmp(other) > 0
        else:
            _cmperror(self, other)

    def _cmp(self, other):
        assert isinstance(other, datetimedelta)
        return _cmp(self._getstate(), other._getstate())

    def __hash__(self):
        if self._hashcode == -1:
            self._hashcode = hash(self._getstate())
        return self._hashcode

    def __bool__(self):
        return (self.years != 0 or
                self.months != 0 or
                self.days != 0 or
                self.seconds != 0 or
                self.microseconds != 0)

    def _getstate(self):
        return (self._years, self._months, self._timedelta)

    def __reduce__(self):
        return (self.__class__, self._getstate())

    def __repr__(self):
        args = []
        if self.years:
            args.append("years=%d" % self.years)
        if self.months:
            args.append("months=%d" % self.months)
        if self.days:
            args.append("days=%d" % self.days)
        if self.seconds:
            args.append("seconds=%d" % self.seconds)
        if self.microseconds:
            args.append("microseconds=%d" % self.microseconds)
        if not args:
            args.append('0')
        return "%s.%s(%s)" % (self.__class__.__module__,
                              self.__class__.__qualname__,
                              ', '.join(args))
