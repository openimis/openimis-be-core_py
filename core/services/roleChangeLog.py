from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from core.models import Role, RoleRight, UserRole

ROLE_CREATED = "ROLE_CREATED"
ATTRIBUTE_CHANGED = "ATTRIBUTE_CHANGED"
RIGHT_GRANTED = "RIGHT_GRANTED"
RIGHT_REVOKED = "RIGHT_REVOKED"
USER_ASSIGNED = "USER_ASSIGNED"
USER_UNASSIGNED = "USER_UNASSIGNED"

TRACKED_ATTRIBUTES = ("name", "alt_language", "is_system", "is_blocked")


@dataclass
class RoleChangeEntry:
    timestamp: datetime
    change_type: str
    field: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    # None means the actor is not recorded for this kind of change. A closed
    # row's audit_user_id belongs to whoever opened it, so reusing it for the
    # closing event would name the wrong person.
    audit_user_id: Optional[int]


def _as_str(value) -> Optional[str]:
    return None if value is None else str(value)


def _creation_entry(role: Role) -> List[RoleChangeEntry]:
    # Creating a role writes no history row, so synthesise the first entry.
    # Caveat: delete_history() overwrites validity_from with the deletion
    # timestamp, so for a deleted role this reports the deletion time.
    return [
        RoleChangeEntry(
            timestamp=role.validity_from,
            change_type=ROLE_CREATED,
            field=None,
            old_value=None,
            new_value=role.name,
            audit_user_id=role.audit_user_id,
        )
    ]


def _attribute_entries(role: Role) -> List[RoleChangeEntry]:
    # save_history() clones the row before the edit is applied and points
    # legacy_id at the live row, so each clone holds the pre-edit values.
    versions = list(
        Role.objects.filter(legacy_id=role.id, validity_to__isnull=False).order_by(
            "validity_to"
        )
    )
    entries = []
    for previous, current in zip(versions, versions[1:] + [role]):
        for field in TRACKED_ATTRIBUTES:
            old, new = getattr(previous, field), getattr(current, field)
            if old != new:
                entries.append(
                    RoleChangeEntry(
                        timestamp=previous.validity_to,
                        change_type=ATTRIBUTE_CHANGED,
                        field=field,
                        old_value=_as_str(old),
                        new_value=_as_str(new),
                        audit_user_id=current.audit_user_id,
                    )
                )
    return entries


def _right_entries(role: Role) -> List[RoleChangeEntry]:
    entries = []
    for role_right in RoleRight.objects.filter(role_id=role.id):
        entries.append(
            RoleChangeEntry(
                timestamp=role_right.validity_from,
                change_type=RIGHT_GRANTED,
                field="right_id",
                old_value=None,
                new_value=str(role_right.right_id),
                audit_user_id=role_right.audit_user_id,
            )
        )
        if role_right.validity_to is not None:
            entries.append(
                RoleChangeEntry(
                    timestamp=role_right.validity_to,
                    change_type=RIGHT_REVOKED,
                    field="right_id",
                    old_value=None,
                    new_value=str(role_right.right_id),
                    audit_user_id=None,
                )
            )
    return entries


def _user_entries(role: Role) -> List[RoleChangeEntry]:
    entries = []
    for user_role in UserRole.objects.filter(role_id=role.id).select_related("user"):
        login = user_role.user.login_name
        entries.append(
            RoleChangeEntry(
                timestamp=user_role.validity_from,
                change_type=USER_ASSIGNED,
                field="user",
                old_value=None,
                new_value=login,
                audit_user_id=user_role.audit_user_id,
            )
        )
        if user_role.validity_to is not None:
            entries.append(
                RoleChangeEntry(
                    timestamp=user_role.validity_to,
                    change_type=USER_UNASSIGNED,
                    field="user",
                    old_value=None,
                    new_value=login,
                    audit_user_id=None,
                )
            )
    return entries


def get_role_change_log(role_uuid: str) -> List[RoleChangeEntry]:
    """Merged, newest-first change feed for a single role.

    Deliberately does not filter on validity_to: set_role_deleted() stamps
    validity_to on the live row, so a validity filter would make the audit log
    of a deleted role unreachable. uuid is unique per row, because both
    save_history() and duplicate_role() assign a fresh one.

    Raises Role.DoesNotExist for an unknown uuid.
    """
    role = Role.objects.get(uuid=role_uuid)
    entries = (
        _creation_entry(role)
        + _attribute_entries(role)
        + _right_entries(role)
        + _user_entries(role)
    )
    return sorted(entries, key=lambda entry: entry.timestamp, reverse=True)
