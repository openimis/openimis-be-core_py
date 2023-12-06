from django.test import TestCase
from core.services.userServices import create_or_update_interactive_user, create_or_update_core_user
from core.test_helpers import create_test_officer
import re
from core.models import InteractiveUser
# Create your tests here.
null = None


class HelpersTest(TestCase):
    test_office = None
    i_user= None
    user = None
    _TEST_USER_NAME = "testhelperusersername"
    _TEST_USER_PASSWORD = "TestPasswordTest2"
    _TEST_DATA_USER = {
    "username": _TEST_USER_NAME,
    "last_name": _TEST_USER_NAME,
    "password": _TEST_USER_PASSWORD,
    "other_names": _TEST_USER_NAME,
    "user_types": "INTERACTIVE",
    "language": "en",
    "roles": [1, 3, 5, 9],
    }
    @classmethod
    def setUpTestData(cls):
        cls.test_officer = create_test_officer(valid=True, custom_props={})
        cls.i_user, i_user_created = create_or_update_interactive_user(user_id=None, data=cls._TEST_DATA_USER, audit_user_id=999, connected=False)
        cls.user, user_created = create_or_update_core_user(None, cls.i_user.username, i_user=cls.i_user)

    def test_defautl(self):
        self.assertEquals(self.user.username, self._TEST_USER_NAME)


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
			"locationId": null,
			"otherNames": "Roger",
			"phone": null,
			"roles": [
				"9"
			],
			"substitutionOfficerId": null,
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
 
        data = self.to_camel_case_key(self._DATA_MUTATION_VARS['variables']['input'])
        #create_or_update_interactive_user(self.user,data)
        #self.user=InteractiveUser.objects.filter(uuid = '28026414-f7dd-48fa-bedd-2f4cce9f9677').first()
        #self.assertEquals(self.user.lastName, "Manal")
        
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
                res[pattern.sub('_', key).lower()]=self.to_camel_case_key(input[key])
            return res    
        else:
            return input
