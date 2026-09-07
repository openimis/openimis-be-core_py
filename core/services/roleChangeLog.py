from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from core.models import InteractiveUser, Role, RoleRight, UserRole

ROLE_CREATED = "ROLE_CREATED"
ROLE_DELETED = "ROLE_DELETED"
ATTRIBUTE_CHANGED = "ATTRIBUTE_CHANGED"
RIGHT_GRANTED = "RIGHT_GRANTED"
RIGHT_REVOKED = "RIGHT_REVOKED"
USER_ASSIGNED = "USER_ASSIGNED"
USER_UNASSIGNED = "USER_UNASSIGNED"

TRACKED_ATTRIBUTES = ("name", "alt_language", "is_system", "is_blocked")

BACKFILL_REASON = "Backfilled from validity dates"


@dataclass
class RoleChangeEntry:
    timestamp: datetime
    change_type: str
    field: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    audit_user_id: Optional[int]
    audit_user_name: Optional[str] = None
    change_reason: Optional[str] = None


def _as_str(value) -> Optional[str]:
    return None if value is None else str(value)


def _actor(record) -> Optional[int]:
    """InteractiveUser id, not core.User's UUID PK."""
    actor = getattr(record, "history_user", None)
    if actor is not None and actor.i_user_id:
        return actor.i_user_id
    return record.audit_user_id


def _reason(record) -> Optional[str]:
    reason = record.history_change_reason
    return None if reason == BACKFILL_REASON else reason


def _entry(record, change_type, field, old_value, new_value) -> RoleChangeEntry:
    return RoleChangeEntry(
        timestamp=record.history_date,
        change_type=change_type,
        field=field,
        old_value=old_value,
        new_value=new_value,
        audit_user_id=_actor(record),
        change_reason=_reason(record),
    )


def _role_entries(role: Role) -> List[RoleChangeEntry]:
    records = list(
        role.history.select_related("history_user").order_by(
            "history_date", "history_id"
        )
    )
    if not records:
        return []

    entries = [
        _entry(records[0], ROLE_CREATED, None, None, records[0].name)
    ]
    for previous, current in zip(records, records[1:]):
        # soft delete: a removal arrives as an update flipping active, not as '-'
        if previous.active and not current.active:
            entries.append(
                _entry(current, ROLE_DELETED, None, None, current.name)
            )
            continue
        for field in TRACKED_ATTRIBUTES:
            old, new = getattr(previous, field), getattr(current, field)
            if old != new:
                entries.append(
                    _entry(
                        current,
                        ATTRIBUTE_CHANGED,
                        field,
                        _as_str(old),
                        _as_str(new),
                    )
                )
    return entries


def _grant_entries(
    records: Iterable,
    field: str,
    granted: str,
    revoked: str,
    subject,
) -> List[RoleChangeEntry]:
    """Turn one row's history into grant and revoke events, one per active flip."""
    entries = []
    by_row = {}
    for record in records:
        by_row.setdefault(record.id, []).append(record)

    for row_id in sorted(by_row):
        row_records = by_row[row_id]
        first = row_records[0]
        entries.append(
            _entry(first, granted if first.active else revoked, field, None, subject(first))
        )
        for previous, current in zip(row_records, row_records[1:]):
            if previous.active == current.active:
                continue
            entries.append(
                _entry(
                    current,
                    granted if current.active else revoked,
                    field,
                    None,
                    subject(current),
                )
            )
    return entries


def _right_entries(role: Role) -> List[RoleChangeEntry]:
    records = (
        RoleRight.history.filter(role_id=role.id)
        .select_related("history_user")
        .order_by("id", "history_date", "history_id")
    )
    return _grant_entries(
        records,
        "right_id",
        RIGHT_GRANTED,
        RIGHT_REVOKED,
        lambda record: str(record.right_id),
    )


def _user_entries(role: Role, include_user_names: bool) -> List[RoleChangeEntry]:
    records = list(
        UserRole.history.filter(role_id=role.id)
        .select_related("history_user")
        .order_by("id", "history_date", "history_id")
    )
    logins = {}
    if include_user_names:
        logins = dict(
            InteractiveUser.objects.filter(
                id__in={record.user_id for record in records}
            ).values_list("id", "login_name")
        )

    def subject(record):
        if not include_user_names:
            return f"#{record.user_id}"
        return logins.get(record.user_id, f"#{record.user_id}")

    return _grant_entries(
        records, "user", USER_ASSIGNED, USER_UNASSIGNED, subject
    )


def _resolve_actor_names(entries: List[RoleChangeEntry]) -> None:
    """Fill in audit_user_name for every entry, in a single query.

    audit_user_id points at InteractiveUser.id. Resolving per entry would be an
    N+1, so all distinct ids are looked up at once. Ids that cannot refer to a
    row are skipped: None (no actor recorded, which is the case for most
    pre-existing data) and -1 (the technical-user sentinel).
    """
    actor_ids = {
        entry.audit_user_id
        for entry in entries
        if entry.audit_user_id is not None and entry.audit_user_id > 0
    }
    if not actor_ids:
        return
    names = dict(
        InteractiveUser.objects.filter(id__in=actor_ids).values_list(
            "id", "login_name"
        )
    )
    for entry in entries:
        entry.audit_user_name = names.get(entry.audit_user_id)


def get_role_change_log(
    role_uuid: str, include_user_names: bool = True
) -> List[RoleChangeEntry]:
    """Merged, newest-first change feed for a single role.

    include_user_names=False keeps logins out of the feed, for callers holding
    the role right but not the user right. Raises Role.DoesNotExist.
    """
    role = Role.objects.get(uuid=role_uuid)
    entries = (
        _role_entries(role)
        + _right_entries(role)
        + _user_entries(role, include_user_names)
    )
    if include_user_names:
        _resolve_actor_names(entries)
    return sorted(entries, key=lambda entry: entry.timestamp, reverse=True)
