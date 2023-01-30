from core.models import Role


def check_role_unique_name(name, uuid=None):
    query = Role.objects.filter(name=name, validity_to__isnull=True)
    if query.exists() and (not uuid or query.get().uuid != uuid):
        return [{"message": "Role code %s already exists" % name}]
    return []
