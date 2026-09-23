import logging

from core.bootstrap import rerun_after_migrate, skip_without_database

logger = logging.getLogger(__name__)

# The ContentType that hosts the business actions, one per app_label.
CONTENT_TYPE_MODEL = "openimisright"

_CODENAME_MAX = 100
_NAME_MAX = 255


def collect_declared_rights():
    """
    ``[(app_label, codename, right_id, entity, action)]`` for every declared action.

    One entry per **action**, not per identifier: that is what lets several
    permissions point at the same right. Read off the modules'
    ``RightsDeclaration``; those that have none yet carry only identifiers and are
    ignored here - their rights stay usable, simply without a django name.
    """
    import sys

    from django.apps import apps as django_apps

    declared = []
    for app_config in django_apps.get_app_configs():
        module = sys.modules.get(type(app_config).__module__)
        rights = getattr(module, "RIGHTS", None) if module else None
        django_perms = getattr(rights, "django_perms", None)
        if not isinstance(django_perms, dict):
            continue
        for entity, actions in django_perms.items():
            for action, pair in actions.items():
                try:
                    name, right_id = pair
                except (TypeError, ValueError):
                    logger.warning(
                        "%s: %s.%s badly declared (%r)", app_config.label, entity, action, pair
                    )
                    continue
                app_label, _, codename = str(name).rpartition(".")
                if not app_label or not codename:
                    logger.warning(
                        "%s: %r is not a django `app_label.codename` name",
                        app_config.label, name,
                    )
                    continue
                declared.append(
                    (app_label, codename[:_CODENAME_MAX], int(right_id), entity, action)
                )
    return declared


@skip_without_database("the rights permission synchronisation", logger)
def sync_right_permissions():
    """Bring the mapping table in line with what the modules declare."""
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from core.models import RightPermission

    declared = collect_declared_rights()
    if not declared:
        return

    # Index of the existing permissions by `app_label.codename`. The model ones
    # first: when django already has the permission, that is the one we want, not
    # ours.
    by_name = {}
    for perm in Permission.objects.select_related("content_type").all():
        key = f"{perm.content_type.app_label}.{perm.codename}"
        is_ours = perm.content_type.model == CONTENT_TYPE_MODEL
        if key not in by_name or not is_ours:
            by_name[key] = perm

    synthetic_cts = {}

    def synthetic_ct(app_label):
        if app_label not in synthetic_cts:
            synthetic_cts[app_label], _ = ContentType.objects.get_or_create(
                app_label=app_label, model=CONTENT_TYPE_MODEL
            )
        return synthetic_cts[app_label]

    created = 0
    resolved = {}
    for app_label, codename, right_id, entity, action in declared:
        key = f"{app_label}.{codename}"
        perm = by_name.get(key)
        if perm is None:
            perm = Permission.objects.create(
                codename=codename,
                name=f"{entity}.{action}"[:_NAME_MAX],
                content_type=synthetic_ct(app_label),
            )
            by_name[key] = perm
            created += 1
        resolved[perm.id] = right_id

    existing = dict(
        RightPermission.objects.values_list("permission_id", "right_id")
    )
    to_add = [
        RightPermission(permission_id=pid, right_id=rid)
        for pid, rid in resolved.items()
        if pid not in existing
    ]
    to_fix = [
        RightPermission(id=None, permission_id=pid, right_id=rid)
        for pid, rid in resolved.items()
        if pid in existing and existing[pid] != rid
    ]
    if to_add:
        RightPermission.objects.bulk_create(to_add, ignore_conflicts=True, batch_size=500)
    if to_fix:
        # a right changed identifier: realign it
        for pid, rid in ((r.permission_id, r.right_id) for r in to_fix):
            RightPermission.objects.filter(permission_id=pid).update(right_id=rid)
    stale = set(existing) - set(resolved)
    if stale:
        RightPermission.objects.filter(permission_id__in=stale).delete()

    _retire_unused_synthetic_permissions(set(resolved), by_name)

    if created or to_add or to_fix or stale:
        logger.info(
            "rights: %d permission(s) created, %d mapping(s) added, "
            "%d realigned, %d obsolete one(s) retired",
            created, len(to_add), len(to_fix), len(stale),
        )
        clear_permission_name_cache()


def _retire_unused_synthetic_permissions(kept_ids, by_name):
    """
    Delete the permissions we had created that no longer serve a purpose.

    Only concerns the rows under an ``openimisright`` ContentType - ours. A row
    becomes useless when the name it carried is now served by django's model
    permission, or when the right is no longer declared.

    Any grants are **transferred** to the permission taking over before deletion:
    deleting a granted permission would silently withdraw access. When there is no
    successor, the row is kept and reported - an orphan row is better than a lost
    grant.
    """
    from django.contrib.auth.models import Permission

    obsolete = (
        Permission.objects.filter(content_type__model=CONTENT_TYPE_MODEL)
        .exclude(id__in=kept_ids)
        .select_related("content_type")
    )
    removed = transferred = kept = 0
    for perm in obsolete:
        successor = by_name.get(f"{perm.content_type.app_label}.{perm.codename}")
        groups = list(perm.group_set.all())
        users = list(perm.user_set.all())
        if groups or users:
            if successor is None or successor.id == perm.id:
                logger.warning(
                    "obsolete permission %s.%s (id=%s) is granted and has no "
                    "successor: kept",
                    perm.content_type.app_label, perm.codename, perm.id,
                )
                kept += 1
                continue
            for group in groups:
                group.permissions.add(successor)
                group.permissions.remove(perm)
            for user in users:
                user.user_permissions.add(successor)
                user.user_permissions.remove(perm)
            transferred += 1
        perm.delete()
        removed += 1
    if removed or kept:
        logger.info(
            "rights: %d obsolete permission(s) retired (%d grant(s) "
            "transferred), %d kept for lack of a successor",
            removed, transferred, kept,
        )


def install(app_config):
    """
    To be called from core's ``ready()``: synchronises now, and again after
    ``migrate`` for the case of a fresh database where the tables do not exist yet.
    """
    sync_right_permissions()
    rerun_after_migrate(
        app_config, sync_right_permissions, "core.rights_sync.sync_right_permissions"
    )


def right_id_for_permission_name(name):
    """
    The identifier of the right this django name (``app_label.codename``) denotes,
    or None.

    The bridge between the two ways of naming a right: the name, which code can
    write, and the integer, which the roles carry. The mapping comes from
    ``core.RightPermission`` - so from the permission's real name, including when
    django is the one that created it.

    Cached: called on the path of every check, while the table only moves at
    startup.
    """
    if "." not in name:
        return None
    return _permission_name_cache().get(name)


_NAME_CACHE = {}


def _permission_name_cache():
    if not _NAME_CACHE:
        from core.models import RightPermission

        try:
            rows = RightPermission.objects.select_related(
                "permission__content_type"
            ).values_list(
                "permission__content_type__app_label",
                "permission__codename",
                "right_id",
            )
            _NAME_CACHE.update(
                {f"{app}.{codename}": rid for app, codename, rid in rows}
            )
        except Exception:
            # database unavailable: nothing cached, the question will be asked again
            return {}
    return _NAME_CACHE


def clear_permission_name_cache():
    _NAME_CACHE.clear()
