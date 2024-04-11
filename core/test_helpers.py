from core.models import Officer, InteractiveUser, User, TechnicalUser, filter_validity
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.services.userServices import create_or_update_officer_villages
from core.services import create_or_update_user_roles
from location.models import Location
from  uuid import uuid4
import json
import time

def create_test_officer(valid=True, custom_props={}, villages = []):

    code = custom_props.pop('code', None)
    uuid = custom_props.pop('uuid', None)
    qs_eo = Officer.objects
    eo = None
    data = {
            "code":  code or "TSTOFF",
            "uuid":uuid,
            "last_name": "Officer",
            "other_names": "Test",
            "validity_to": None if valid else "2019-06-01",
            "audit_user_id": -1,
            "phone": "0000110100",
            **(custom_props if custom_props else {})
        }
    if code:
        qs_eo = qs_eo.filter(code=code)
    if uuid:
        qs_eo = qs_eo.filter(uuid=uuid)
    eo = None        
    if code or uuid:
        eo = qs_eo.first()
    if eo:
        data['uuid']=eo.uuid
        eo.update(data)
    else:
        data['uuid']=uuid4()
        eo =   Officer.objects.create(**data)
    if villages == []:
        villages == Location.objects.filter(*filter_validity(), type = 'V').first()
    if eo:
        result = create_or_update_officer_villages(eo, [v.id for v in villages], 1)
        return eo

def create_test_interactive_user(username='TestInteractiveTest', password="Test1234", roles=None, custom_props=None):
    if roles is None:
        roles = [7, 1, 2, 3, 4, 5, 6]
    i_user = InteractiveUser.objects.create(
        **{
            "language_id": "en",
            "last_name": "TestLastName",
            "other_names": "Test Other Names",
            "login_name": username,
            "audit_user_id": -1,
            "role_id": roles[0],
            **(custom_props if custom_props else {})
        }
    )
    i_user.set_password(password)
    i_user.save()
    create_or_update_user_roles(i_user, roles, None)
    return User.objects.create(
        username=username,
        i_user=i_user,
    )


def create_test_technical_user(
        username='TestAdminTechnicalTest', password="S\/pe®Pąßw0rd""", super_user=False,
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
        elif isinstance(obj1 , (float, int)) or (isinstance(obj1, str) and obj1.isnumeric()) \
                and isinstance(obj2 , (float, int)) or (isinstance(obj2, str) and obj2.isnumeric()):
            # Compare floating-point numbers with a tolerance for decimal precision
            return round(float(obj1), 2) == round(float(obj2), 2)

        # Compare other types directly
        return obj1 == obj2

    return recursive_compare(dict1, dict2)



def AssertMutation(test_obj,mutation_uuid, token ):
    return openIMISGraphQLTestCase().get_mutation_result(mutation_uuid, token)


