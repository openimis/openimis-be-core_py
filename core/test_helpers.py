from core.models import Officer, InteractiveUser, User, TechnicalUser, Role, RoleRight, filter_validity
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.models.user import ClaimAdmin
from core.services.userServices import (
    create_or_update_officer_villages,
    create_or_update_interactive_user,
    create_or_update_core_user,
)
from core.services import create_or_update_user_roles
from core.utils import collect_all_gql_permissions
from location.models import Location
from location.test_helpers import create_test_health_facility
from uuid import uuid4
import datetime


def create_test_officer(valid=True, custom_props=None, villages=[]):
    if custom_props is None:
        custom_props = {}
    else:
        custom_props = {k: v for k, v in custom_props.items() if hasattr(Officer, k)}

    code = custom_props.pop("code", None)
    uuid = custom_props.pop("uuid", None)
    qs_eo = Officer.objects
    eo = None
    data = {
        "code": code or "TSTOFF",
        "uuid": uuid,
        "last_name": "Officer",
        "other_names": "Test",
        "validity_to": None if valid else "2019-06-01",
        "audit_user_id": -1,
        "phone": "0000110100",
        **custom_props,
    }

    if code:
        qs_eo = qs_eo.filter(code=code)
    if uuid:
        qs_eo = qs_eo.filter(uuid=uuid)
    eo = None
    if code or uuid:
        eo = qs_eo.first()
    if eo:
        data["uuid"] = eo.uuid
        eo.update(data)
    else:
        data["uuid"] = uuid4()
        eo = Officer.objects.create(**data)

    if not villages:
        villages == Location.objects.filter(*filter_validity(), type="V").first()
    if eo:
        _ = create_or_update_officer_villages(eo, [v.id for v in villages], 1)
        return eo


def create_test_interactive_user(
    username="TestInteractiveTest",
    password="admin123",
    roles=None,
    custom_props=None,
):
    if custom_props is None:
        custom_props = {}
    else:
        custom_props = {
            k: v for k, v in custom_props.items() if hasattr(InteractiveUser, k)
        }
    if roles is None:
        roles = [7, 1, 2, 3, 4, 5, 6]
    user = None
    i_user = InteractiveUser.objects.filter(login_name=username).first()

    if i_user:
        # TODO add custom prop to existing user
        user = User.objects.filter(i_user=i_user).first()
    else:
        user = User.objects.filter(
            username=username,
        ).first()
        if user and user.i_user:
            i_user = user.i_user
        else:
            i_user = InteractiveUser.objects.create(
                **{
                    "language_id": "en",
                    "last_name": "TestLastName",
                    "other_names": "Test Other Names",
                    "login_name": username,
                    "audit_user_id": -1,
                    "role_id": roles[0],
                    **custom_props,
                }
            )

    if not user:
        user = User.objects.create(
            username=username,
            i_user=i_user,
        )
    i_user.set_password(password)
    i_user.save()
    create_or_update_user_roles(i_user, roles, None)
    return user


def create_test_technical_user(
    username="TestAdminTechnicalTest",
    password="S\\/pe®Pąßw0rd" "",
    super_user=False,
    custom_tech_user_props={},
    custom_core_user_props={},
):
    custom_tech_user_props["password"] = password
    t_user, t_user_created = TechnicalUser.objects.get_or_create(
        **{
            "username": username,
            "email": "test_tech_user@openimis.org",
            "is_staff": super_user,
            "is_superuser": super_user,
            **(custom_tech_user_props),
        }
    )
    # Just for safety and retrieving the User because TechnicalUser will automatically create its User
    custom_core_user_props["password"] = password
    core_user, core_user_created = User.objects.get_or_create(
        username=username, t_user=t_user, **(custom_core_user_props)
    )
    return core_user


def create_test_claim_admin(custom_props=None):
    if custom_props is None:
        custom_props = {}
    from core import datetime

    custom_props = {k: v for k, v in custom_props.items() if hasattr(ClaimAdmin, k)}
    if (
        "health_facility" not in custom_props
        and "health_facility_id" not in custom_props
    ):
        custom_props["health_facility"] = create_test_health_facility(
            code=None, location_id=None
        )

    code = custom_props.pop("code", "TST-CA")
    uuid = custom_props.pop("uuid", uuid4())
    ca = None
    qs_ca = ClaimAdmin.objects
    data = {
        "code": code,
        "uuid": uuid,
        "last_name": "LastAdmin",
        "other_names": "JoeAdmin",
        "email_id": "joeadmin@lastadmin.com",
        "phone": "+12027621401",
        "has_login": False,
        "audit_user_id": 1,
        "validity_from": datetime.datetime(2019, 6, 1),
        **custom_props,
    }
    if code:
        qs_ca = qs_ca.filter(code=code)
    if uuid:
        qs_ca = qs_ca.filter(uuid=uuid)

    if code or uuid:
        ca = qs_ca.first()
    if ca:
        data["uuid"] = ca.uuid
        ca.objects.update(**data)
        return ca
    else:
        return ClaimAdmin.objects.create(**data)


def compare_dicts(dict1, dict2):
    def recursive_compare(obj1, obj2):
        if isinstance(obj1, dict) and isinstance(obj2, dict):
            # Check keys
            if set(obj1.keys()) != set(obj2.keys()):
                return False

            # Recursively compare values
            for key in obj1.keys():
                if not recursive_compare(obj1[key], obj2[key]):
                    return False

            return True
        elif isinstance(obj1, list) and isinstance(obj2, list):
            # Check list length
            if len(obj1) != len(obj2):
                return False

            # Recursively compare list elements
            for item1, item2 in zip(obj1, obj2):
                if not recursive_compare(item1, item2):
                    return False

            return True
        elif (
            isinstance(obj1, (float, int))
            or (isinstance(obj1, str) and obj1.isnumeric())
            and isinstance(obj2, (float, int))
            or (isinstance(obj2, str) and obj2.isnumeric())
        ):
            # Compare floating-point numbers with a tolerance for decimal precision
            return round(float(obj1), 2) == round(float(obj2), 2)

        # Compare other types directly
        return obj1 == obj2

    return recursive_compare(dict1, dict2)


def AssertMutation(test_obj, mutation_uuid, token):
    return openIMISGraphQLTestCase().get_mutation_result(mutation_uuid, token)


class LogInHelper:
    def __init__(self):
        self.test_user_name = "Admin"
        self.test_user_password = "TestPasswordTest2@"
        self.test_data_user = {
            "username": self.test_user_name,
            "last_name": self.test_user_name,
            "password": self.test_user_password,
            "other_names": self.test_user_name,
            "user_types": "INTERACTIVE",
            "language": "en",
            "roles": [1, 3, 5, 9],
        }

    def get_or_create_user_api(self, **kwargs):
        username = kwargs.get("username") or self.test_user_name
        user = User.objects.filter(username=username).first()
        if user is None:
            user = self._create_user_interactive_core(**kwargs)
        return user

    def _create_user_interactive_core(self, **kwargs):
        username = kwargs.get("username") or self.test_user_name
        i_user, i_user_created = create_or_update_interactive_user(
            user_id=None,
            data={**self.test_data_user, **kwargs},
            audit_user_id=999,
            connected=False,
        )
        create_or_update_core_user(user_uuid=None, username=username, i_user=i_user)
        return User.objects.get(username=username)


def create_test_role(perm_names, name=None, is_system=0, is_blocked=False, custom_props=None):
    """
    Create a test role with permissions specified by name as they appear in the module DEFAULT config.

    Args:
        perm_names: List of permission names (e.g., ["gql_query_roles_perms", "gql_mutation_create_roles_perms"])
        name: Optional role name, defaults to "TestRole"
        is_system: System role flag (default 0 for non-system)
        is_blocked: Whether role is blocked (default False)
        custom_props: Additional properties for the role

    Returns:
        Role object
    """
    if custom_props is None:
        custom_props = {}
    else:
        custom_props = {k: v for k, v in custom_props.items() if hasattr(Role, k)}

    if name is None:
        name = "TestRole"

    # Collect all permissions from DEFAULT configs
    permissions_dict = collect_all_gql_permissions()

    # Flatten permission IDs for the given names
    right_ids = []
    for app_perms in permissions_dict.values():
        for perm_name, perm_ids in app_perms.items():
            if perm_name in perm_names:
                right_ids.extend(perm_ids)

    # Remove duplicates
    right_ids = list(set(right_ids))

    # Create the role
    role_data = {
        "name": name,
        "is_system": is_system,
        "is_blocked": is_blocked,
        "audit_user_id": -1,
        "validity_from": datetime.datetime.now(),
        **custom_props,
    }

    role = Role.objects.create(**role_data)

    # Create role rights
    for right_id in right_ids:
        RoleRight.objects.create(
            role=role,
            right_id=right_id,
            audit_user_id=-1,
            validity_from=datetime.datetime.now(),
        )

    return role
