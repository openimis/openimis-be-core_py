from core.models import Officer, InteractiveUser, User
from core.services import create_or_update_user_roles


def create_test_officer(valid=True, custom_props=None):
    officer = Officer.objects.create(
        **{
            "code": "TSTOFF",
            "last_name": "Officer",
            "other_names": "Test",
            "validity_to": None if valid else "2019-06-01",
            "audit_user_id": -1,
            **(custom_props if custom_props else {})
        }
    )
    return officer


def create_test_interactive_user(username, password="Test1234", roles=None, custom_props=None):
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
