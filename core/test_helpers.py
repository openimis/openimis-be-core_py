from core.models import Officer


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
