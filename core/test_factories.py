import datetime

import factory
from django.core.cache import cache

from core.models import Role, RoleRight
from core.utils import collect_all_gql_permissions


def role_right_ids(perm_names):
    """Resolve permission names as they appear in the module DEFAULT configs into right ids."""
    flat_perms = {}
    for app_perms in collect_all_gql_permissions().values():
        flat_perms.update(app_perms)

    right_ids = []
    for perm_name in perm_names:
        if perm_name not in flat_perms:
            # message is asserted verbatim by core.tests.test_create_test_role
            raise Exception(f"Permission {perm_name} not found")
        right_ids.extend(flat_perms[perm_name])

    return list(set(right_ids))


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role

    name = factory.Sequence(lambda n: f"TestRole{n}")
    is_system = 0
    is_blocked = False
    audit_user_id = -1
    validity_from = factory.LazyFunction(datetime.datetime.now)

    @factory.post_generation
    def perm_names(self, create, extracted, **kwargs):
        if not create or not extracted:
            return
        for right_id in role_right_ids(extracted):
            RoleRightFactory(role=self, right_id=right_id)
        # rights are cached per user, so a role built mid-test stays invisible without this
        cache.clear()


class RoleRightFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoleRight

    role = factory.SubFactory(RoleFactory)
    right_id = 1
    audit_user_id = -1
    validity_from = factory.LazyFunction(datetime.datetime.now)
