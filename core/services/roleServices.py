from core.models import Role


def check_unique_name(name):
    if Role.objects.filter(name=name, validity_to__isnull=True).exists():
        return [{"message": "Location code %s already exists" % name}]
    return []
