import datetime
from collections import defaultdict

from django.db import migrations

BACKFILL_REASON = "Backfilled from validity dates"

_HISTORY_META = {
    "history_id",
    "history_date",
    "history_change_reason",
    "history_type",
    "history_user",
    "history_user_id",
}

_FAR_FUTURE = datetime.datetime.max


def _history_row(historical_model, record, history_date, history_type, active):
    data = {
        field.attname: getattr(record, field.attname)
        for field in record._meta.fields
        if field.attname not in _HISTORY_META
    }
    data["active"] = active
    return historical_model(
        history_date=history_date,
        history_type=history_type,
        history_change_reason=BACKFILL_REASON,
        **data,
    )


def _role_history(apps):
    """One logical role is a chain of cloned rows; only its oldest link is a creation."""
    role_model = apps.get_model("core", "Role")
    historical = apps.get_model("core", "HistoricalRole")

    chains = defaultdict(list)
    for row in role_model.objects.all().iterator():
        chains[row.legacy_id or row.id].append(row)

    rows = []
    for chain in chains.values():
        chain.sort(key=lambda r: (r.validity_to or _FAR_FUTURE, r.id))
        for index, row in enumerate(chain):
            rows.append(
                _history_row(
                    historical,
                    row,
                    history_date=row.validity_from,
                    history_type="+" if index == 0 else "~",
                    active=row.validity_to is None,
                )
            )
    return historical, rows


def _grant_history(apps, model_name):
    """Every rights/assignment row is one grant: opens at validity_from, closes at validity_to."""
    model = apps.get_model("core", model_name)
    historical = apps.get_model("core", f"Historical{model_name}")

    rows = []
    for record in model.objects.all().iterator():
        rows.append(
            _history_row(
                historical,
                record,
                history_date=record.validity_from,
                history_type="+",
                active=True,
            )
        )
        if record.validity_to is not None:
            rows.append(
                _history_row(
                    historical,
                    record,
                    history_date=record.validity_to,
                    history_type="~",
                    active=False,
                )
            )
    return historical, rows


def forwards(apps, schema_editor):
    for model_name in ("Role", "RoleRight", "UserRole"):
        model = apps.get_model("core", model_name)
        # derived, never left on its default: filter_queryset() sits on the rights hot path
        model.objects.filter(validity_to__isnull=True).update(active=True)
        model.objects.filter(validity_to__isnull=False).update(active=False)

    # rebuilt while validity_from still exists: OpenIMISModel has no date_created
    for historical, rows in (
        _role_history(apps),
        _grant_history(apps, "RoleRight"),
        _grant_history(apps, "UserRole"),
    ):
        historical.objects.bulk_create(rows, batch_size=500)


def backwards(apps, schema_editor):
    for model_name in ("Role", "RoleRight", "UserRole"):
        apps.get_model("core", f"Historical{model_name}").objects.filter(
            history_change_reason=BACKFILL_REASON
        ).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0038_roles_to_history")]

    operations = [migrations.RunPython(forwards, backwards)]
