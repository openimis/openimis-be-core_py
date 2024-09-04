from core.models import Officer, InteractiveUser, User, TechnicalUser, filter_validity
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.services.userServices import create_or_update_officer_villages, create_or_update_interactive_user, \
    create_or_update_core_user
from core.services import create_or_update_user_roles
from location.models import Location
from uuid import uuid4


def create_test_officer(valid=True, custom_props=None, villages=[]):
    if custom_props is None:
        custom_props = {}
    else:
        custom_props = {k: v for k, v in custom_props.items() if hasattr(Officer, k)}

    code = custom_props.pop('code', None)
    uuid = custom_props.pop('uuid', None)
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
        **custom_props
    }

    if code:
        qs_eo = qs_eo.filter(code=code)
    if uuid:
        qs_eo = qs_eo.filter(uuid=uuid)
    eo = None
    if code or uuid:
        eo = qs_eo.first()
    if eo:
        data['uuid'] = eo.uuid
        eo.update(data)
    else:
        data['uuid'] = uuid4()
        eo = Officer.objects.create(**data)
    
    if not villages:
        villages == Location.objects.filter(*filter_validity(), type='V').first()
    if eo:
        _ = create_or_update_officer_villages(eo, [v.id for v in villages], 1)
        return eo


def create_test_interactive_user(username='TestInteractiveTest', password="S\\:\\/pe®Pąßw0rd""", roles=None,
                                 custom_props=None):
    if custom_props is None:
        custom_props = {}
    else:
        custom_props = {k: v for k, v in custom_props.items() if hasattr(InteractiveUser, k)}
    if roles is None:
        roles = [7, 1, 2, 3, 4, 5, 6]
    user = None
    i_user = InteractiveUser.objects.filter(login_name=username).first()
    if i_user:
        # TODO add custom prop to existing user
        user = User.objects.filter(i_user=i_user).first()
    else:
        i_user = InteractiveUser.objects.create(
            **{
                "language_id": "en",
                "last_name": "TestLastName",
                "other_names": "Test Other Names",
                "login_name": username,
                "audit_user_id": -1,
                "role_id": roles[0],
                **custom_props
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
        username='TestAdminTechnicalTest', password="S\\/pe®Pąßw0rd""", super_user=False,
        custom_tech_user_props={}, custom_core_user_props={}):
    custom_tech_user_props['password'] = password
    t_user, t_user_created = TechnicalUser.objects.get_or_create(
        **{
            "username": username,
            "email": "test_tech_user@openimis.org",
            "is_staff": super_user,
            "is_superuser": super_user,
            **(custom_tech_user_props)
        }
    )
    # Just for safety and retrieving the User because TechnicalUser will automatically create its User
    custom_core_user_props['password'] = password
    core_user, core_user_created = User.objects.get_or_create(
        username=username,
        t_user=t_user,
        **(custom_core_user_props)
    )
    return core_user


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
        elif isinstance(obj1, (float, int)) or (isinstance(obj1, str) and obj1.isnumeric()) \
                and isinstance(obj2, (float, int)) or (isinstance(obj2, str) and obj2.isnumeric()):
            # Compare floating-point numbers with a tolerance for decimal precision
            return round(float(obj1), 2) == round(float(obj2), 2)

        # Compare other types directly
        return obj1 == obj2

    return recursive_compare(dict1, dict2)


def AssertMutation(test_obj, mutation_uuid, token):
    return openIMISGraphQLTestCase().get_mutation_result(mutation_uuid, token)


class LogInHelper:
    def __init__(self):
        self.test_user_name = "TestUserTest2"
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
        username = kwargs.get('username') or self.test_user_name
        user = User.objects.filter(username=username).first()
        if user is None:
            user = self._create_user_interactive_core(**kwargs)
        return user

    def _create_user_interactive_core(self, **kwargs):
        username = kwargs.get('username') or self.test_user_name
        i_user, i_user_created = create_or_update_interactive_user(
            user_id=None, data={**self.test_data_user, **kwargs}, audit_user_id=999, connected=False)
        create_or_update_core_user(
            user_uuid=None, username=username, i_user=i_user)
        return User.objects.get(username=username)
