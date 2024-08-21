from django.test import TestCase
from core.test_helpers import create_test_officer, LogInHelper
import re
from core.models import InteractiveUser, Officer, User


class HelpersTest(TestCase):

    def test_create_test_officer(self):
        count_before = Officer.objects.count()
        user = create_test_officer(valid=True, custom_props={})
        self.assertTrue(type(user) is Officer)
        count_after = Officer.objects.count()
        self.assertEquals(count_after, count_before + 1)

    def test_login_helper(self):
        count_before = InteractiveUser.objects.count()
        login_helper = LogInHelper()
        user = login_helper.get_or_create_user_api()
        self.assertTrue(type(user) is User)
        count_after = InteractiveUser.objects.count()
        self.assertEquals(count_after, count_before + 1)


class GQLTest(TestCase):
    _DATA_MUTATION_VARS = {
        "variables": {
            "input": {
                "birthDate": "1990-10-18",
                "clientMutationId": "6a7ff306-24d0-4b51-a383-c072e764e842",
                "clientMutationLabel": "Update user",
                "districts": [
                    "20"
                ],
                "email": "Admin@admin.com",
                "healthFacilityId": "6",
                "language": "en",
                "lastName": "Manal",
                "locationId": None,
                "otherNames": "Roger",
                "phone": None,
                "roles": [
                    "9"
                ],
                "substitutionOfficerId": None,
                "username": "VHOS0011",
                "userTypes": [
                    "INTERACTIVE",
                    "CLAIM_ADMIN"
                ],
                "uuid": "28026414-f7dd-48fa-bedd-2f4cce9f9677"
            }
        }
    }

    def test_save(self):

        _ = self.to_camel_case_key(self._DATA_MUTATION_VARS['variables']['input'])
        # create_or_update_interactive_user(self.user,data)
        # self.user=InteractiveUser.objects.filter(uuid = '28026414-f7dd-48fa-bedd-2f4cce9f9677').first()
        # self.assertEquals(self.user.lastName, "Manal")

    def to_camel_case_key(self, input):
        pattern = re.compile(r'(?<!^)(?=[A-Z]|[0-9]+)')
        if isinstance(input, list):
            res = []
            for elm in input:
                res.append(self.to_camel_case_key(elm))
            return res
        elif isinstance(input, dict):
            res = {}
            for key in input:
                res[pattern.sub('_', key).lower()] = self.to_camel_case_key(input[key])
            return res
        else:
            return input
