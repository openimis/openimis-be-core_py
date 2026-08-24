from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from core.models import InteractiveUser, Role, RoleRight, UserRole

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
    # Resolved login name, filled in by _resolve_actor_names(). Stays None when
    # there is nothing to resolve: no actor recorded, or the -1 sentinel that
    # User.id_for_audit returns for a user with no InteractiveUser.
    audit_user_name: Optional[str] = None


def _as_str(value) -> Optional[str]:
    return None if value is None else str(value)


def _creation_entry(role: Role, versions: List[Role]) -> List[RoleChangeEntry]:
    # Creating a role writes no history row, so synthesise the first entry.
    # delete_history() overwrites validity_from on the live row with the
    # deletion timestamp, so the oldest clone is the only row that still
    # carries the creation time.
    created_at = versions[0].validity_from if versions else role.validity_from
    return [
        RoleChangeEntry(
            timestamp=created_at,
            change_type=ROLE_CREATED,
            field=None,
            old_value=None,
            new_value=role.name,
            audit_user_id=role.audit_user_id,
        )
    ]


def _versions(role: Role) -> List[Role]:
    """Older revisions of the role, oldest first.

    save_history() clones the row before the edit is applied and points
    legacy_id at the live row, so each clone holds the pre-edit values.
    """
    return list(
        Role.objects.filter(legacy_id=role.id, validity_to__isnull=False).order_by(
            "validity_to"
        )
    )


def _attribute_entries(role: Role, versions: List[Role]) -> List[RoleChangeEntry]:
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
    for role_right in RoleRight.objects.filter(role_id=role.id).order_by("id"):
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
    user_roles = (
        UserRole.objects.filter(role_id=role.id)
        .select_related("user")
        .order_by("id")
    )
    for user_role in user_roles:
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


def get_role_change_log(role_uuid: str) -> List[RoleChangeEntry]:
    """Merged, newest-first change feed for a single role.

    Deliberately does not filter on validity_to: set_role_deleted() stamps
    validity_to on the live row, so a validity filter would make the audit log
    of a deleted role unreachable. uuid is unique per row, because both
    save_history() and duplicate_role() assign a fresh one.

    Entries sharing a timestamp keep the order of the rows they came from:
    sorted() is stable and every source is ordered, so a page boundary inside
    a group of equal timestamps stays in the same place between requests.

    Raises Role.DoesNotExist for an unknown uuid.
    """
    role = Role.objects.get(uuid=role_uuid)
    versions = _versions(role)
    entries = (
        _creation_entry(role, versions)
        + _attribute_entries(role, versions)
        + _right_entries(role)
        + _user_entries(role)
    )
    _resolve_actor_names(entries)
    return sorted(entries, key=lambda entry: entry.timestamp, reverse=True)
