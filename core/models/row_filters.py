"""Which rows a query returns, independently of who asks (OP-2029).

Two dimensions, each with a default:

- ``validity``: NOW (default), ALL, DELETED_NOW, at(date), between(from, to).
  NOW is the live, non-deleted state; ALL adds deleted rows; DELETED_NOW is
  the deleted rows only. A date or range asks for the business validity, and
  only exists on families that carry one (ValidityMixin, or a VersionedModel
  declaring ``business_versioned``).
- ``audits``: NONE (default), ALL, at(date), between(from, to).
  The audit trail of earlier states. at(date) is the state as of that date,
  between(from, to) the audit entries dated in that range.

Each model family translates the two values into its own markers in
``filter_rows``; this module only holds the values.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

from django.db.models import Q

#: The one spelling of "no rows" inside a filter(); querysets use no_rows().
NO_ROWS = Q(pk__in=[])


@dataclass(frozen=True)
class _RowFilter:
    kind: str
    start: Optional[datetime] = None
    end: Optional[datetime] = None

    @property
    def dated(self):
        return self.kind in ("at", "between")

    def range(self):
        """The (start, end) bounds of a dated value; at(d) is (d, d)."""
        return self.start, self.end


def _at(cls, date):
    if date is None:
        raise ValueError(f"{cls.__name__}.at() needs a date")
    return cls("at", date, date)


def _between(cls, start, end):
    if start is None and end is None:
        raise ValueError(f"{cls.__name__}.between() needs at least one bound")
    if start is not None and end is not None and start > end:
        raise ValueError(f"{cls.__name__}.between(): {start} is after {end}")
    return cls("between", start, end)


class Validity(_RowFilter):
    NOW = None
    ALL = None
    DELETED_NOW = None
    at = classmethod(_at)
    between = classmethod(_between)


class Audits(_RowFilter):
    NONE = None
    ALL = None
    at = classmethod(_at)
    between = classmethod(_between)


Validity.NOW = Validity("now")
Validity.ALL = Validity("all")
Validity.DELETED_NOW = Validity("deleted_now")
Audits.NONE = Audits("none")
Audits.ALL = Audits("all")


def refuse_date(model, validity):
    raise ValueError(
        f"{model.__name__} has no business validity; "
        f"use NOW, ALL or DELETED_NOW instead of {validity.kind}"
    )


def day_bounds(start, end):
    """Widen bare dates to whole days, so at(date) means that whole day."""
    if isinstance(start, date) and not isinstance(start, datetime):
        start = datetime.combine(start, time.min)
    if isinstance(end, date) and not isinstance(end, datetime):
        end = datetime.combine(end, time.max)
    return start, end
