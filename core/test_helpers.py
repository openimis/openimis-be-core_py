from core.models import (
    Officer,
    InteractiveUser,
    User,
    TechnicalUser,
    Language,
    Role,
)
from django.core.cache import cache
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.models.user import ClaimAdmin
from core.services.userServices import (
    create_or_update_officer_villages,
)
from core.services import create_or_update_user_roles
from core.utils import set_current_user, clear_history_context, clear_current_user
from core.test_factories import ROLE_PRESETS, RoleFactory, RoleRightFactory, role_right_ids
from django.core.cache import caches
from location.models import Location
from location.test_helpers import create_test_health_facility
from uuid import uuid4
from django.core.exceptions import ValidationError


def create_test_language(code="en", name="English", sort_order=1, custom_props=None):
    """
    Create a test language in the database.

    Args:
        code: Language code (primary key)
        name: Language name
        sort_order: Sort order for the language
        custom_props: Additional properties for the language

    Returns:
        Language object
    """
    if custom_props is None:
        custom_props = {}
    else:
        custom_props = {k: v for k, v in custom_props.items() if hasattr(Language, k)}

    # Check if language already exists
    existing_language = Language.objects.filter(code=code).first()
    if existing_language:
        return existing_language

    # Create new language
    language_data = {
        "code": code,
        "name": name,
        "sort_order": sort_order,
        **custom_props,
    }

    return Language.objects.create(**language_data)


def create_test_officer(valid=True, custom_props=None, villages=[]):
    if custom_props is None:
        custom_props = {}
    else:
        custom_props = {k: v for k, v in custom_props.items() if hasattr(Officer, k)}

    code = custom_props.pop("code", None)
    uuid = custom_props.pop("uuid", None)
    qs_eo = Officer.objects
    eo = None
    code = code or "TSTOFF"
    data = {
        "code": code,
        "uuid": uuid,
        "last_name": "Officer",
        "other_names": "Test",
        "validity_to": None if valid else "2019-06-01",
        "audit_user_id": -1,
        "phone": "0000110100",
        **custom_props,
    }

    eo = None
    if uuid:
        qs_eo = qs_eo.filter(uuid=uuid)
    elif code:
        qs_eo = qs_eo.filter(code=code)

    if code or uuid:
        eo = qs_eo.first()
    if eo:
        data["uuid"] = eo.uuid
        eo.update(**data)
    else:
        data["uuid"] = uuid4()
        eo = Officer.objects.create(**data)

    if not villages:
        villages == Location.objects.filter(*Location.filter_validity(), type="V").first()
    if eo:
        _ = create_or_update_officer_villages(eo, [v.id for v in villages], 1)
        return eo


def create_test_interactive_user(
    username="TestInteractiveTest",
    password="admin123",
    roles=None,
    custom_props=None,
    **kwargs
):
    if custom_props is None:
        custom_props = {}
    clear_current_user()
    clear_history_context()
    caches["default"].clear()
    user_field_names = {
        f.name for f in User._meta.get_fields()
        if getattr(f, "concrete", False) and not f.many_to_many
    }
    user_props = {k: v for k, v in custom_props.items() if k in user_field_names}
    iuser_props = {
        k: v for k, v in custom_props.items()
        if hasattr(InteractiveUser, k) and k not in ['is_staff', 'is_superuser']
    }
    # Handle language field specially - convert code to Language instance
    if "language" in iuser_props:
        language_value = iuser_props["language"]
        if isinstance(language_value, str):
            iuser_props["language"] = create_test_language(code=language_value)
        # If it's already a Language instance, keep it as is
    elif "language_id" in iuser_props:
        language_code = iuser_props["language_id"]
        iuser_props["language"] = create_test_language(code=language_code)
        del iuser_props["language_id"]
    if roles is None:
        # Create a test role with default permissions instead of hardcoded role IDs
        roles = [create_admin_role().id]
        if "is_superuser" not in user_props:
            user_props["is_superuser"] = True
    user = None
    i_user = InteractiveUser.objects.filter(login_name=username, *InteractiveUser.filter_validity()).first()

    if i_user:
        # Update existing i_user with custom props
        if iuser_props:
            for key, value in iuser_props.items():
                setattr(i_user, key, value)
        try:
            i_user.save()
        except ValidationError:
            # unchanged
            pass
        user = User.objects.filter(i_user=i_user, *User.filter_validity()).first()
        # Update existing user if found and if there are custom props for User model
        if not user:
            user = User.objects.filter(username=username, *User.filter_validity()).first()
            if user:
                user.i_user = i_user
        if user:
            if user_props:
                for key, value in user_props.items():
                    setattr(user, key, value)
                user.save(silent=True)
    else:
        user = User.objects.filter(
            username=username, *User.filter_validity()
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
                    "role_id": roles[0] if roles else None,
                    **iuser_props,
                }
            )

    if not user:
        user = User(
            username=username,
            i_user=i_user,
            **user_props
        )
    try:
        user.save()
    except ValidationError:
        # unchanged
        pass
    i_user.set_password(password, private_key=i_user.private_key)
    try:
        i_user.save()
    except ValidationError:
        # unchanged
        pass

    create_or_update_user_roles(i_user, roles, None)
    cache.clear()
    set_current_user(user)
    return user


def create_test_technical_user(
    username="TestAdminTechnicalTest",
    password="S\\/pe®Pąßw0rd" "",
    staff=False,
    super_user=False,
    custom_tech_user_props={},
    custom_core_user_props={},
):
    custom_tech_user_props["password"] = password
    t_user, t_user_created = TechnicalUser.objects.get_or_create(
        **{
            "username": username,
            "email": "test_tech_user@openimis.org",
            "is_staff": staff,
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
            "language": "en"
        }

    def get_or_create_user_api(self, **kwargs):
        return create_test_interactive_user(**kwargs)


def create_enrolment_officer_role():
    return _create_preset_role("EnrolmentOfficer")


def create_claim_admin_role():
    return _create_preset_role("ClaimAdministrator")


def create_test_role(perm_names=[], name=None, is_system=0, is_blocked=False, custom_props=None):
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

    existing_role = Role.objects.filter(name=name, *Role.filter_validity()).first()
    if existing_role:
        return existing_role

    # resolved before the role exists, so an unknown permission name leaves nothing behind
    right_ids = role_right_ids(perm_names)

    # single dict, so custom_props keeps overriding the defaults instead of colliding with them
    role = RoleFactory(**{"name": name, "is_system": is_system, "is_blocked": is_blocked, **custom_props})
    for right_id in right_ids:
        RoleRightFactory(role=role, right_id=right_id)
    cache.clear()

    return role


def _create_preset_role(preset):
    spec = ROLE_PRESETS[preset]
    return create_test_role(perm_names=spec["perm_names"], name=preset, is_system=spec["is_system"])


def create_admin_role(name="IMIS Administrator", is_system=0, is_blocked=False, custom_props=None):
    existing_role = Role.objects.filter(is_system=64, *Role.filter_validity()).first()
    if existing_role:
        return existing_role
    perm_names = []
    return create_test_role(perm_names, name=name, is_system=64, is_blocked=is_blocked, custom_props=custom_props)


def create_manager_role():
    return _create_preset_role("Manager")


def create_accountant_role():
    return _create_preset_role("Accountant")


def create_clerk_role():
    return _create_preset_role("Clerk")


def create_medical_officer_role():
    return _create_preset_role("MedicalOfficer")


def create_scheme_admin_role():
    return _create_preset_role("SchemeAdministrator")


def create_imis_admin_role():
    """
    Create the IMIS Administrator role with extensive permissions.
    This role has admin-level access including user and role management.
    """
    return Role.objects.filter(is_system=64, *Role.filter_validity()).first()


def create_receptionist_role():
    return _create_preset_role("Receptionist")


def create_claim_contributor_role():
    return _create_preset_role("ClaimContributor")


def create_hf_admin_role():
    return _create_preset_role("HFAdministrator")


def create_offline_admin_role():
    return _create_preset_role("OfflineAdministrator")
