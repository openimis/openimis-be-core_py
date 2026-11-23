"""OP-3317 at the GraphQL level: core connections take isDeleted / showHistory, the
legacy arguments keep their meaning, and validity is applied by the models.

The resolvers state what their legacy arguments meant (legacy_row_filters); they
no longer filter validity themselves. Officer connections whose resolver never
filtered (enrolmentOfficers...) keep hiding deleted officers: the filter
OfficerGQLType used to apply is Officer's default now.
"""
import json

from core.models import ClaimAdmin, Officer, Role
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.test_helpers import (
    create_test_claim_admin, create_test_interactive_user, create_test_officer, create_test_role)


class CoreConnectionRowFilterArgsTest(openIMISGraphQLTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = create_test_interactive_user(username="rowArgsCoreAdmin")
        cls.token = cls.get_jwt_token(cls.admin)
        create_test_role(name="RowArgsRole live")
        deleted = create_test_role(name="RowArgsRole deleted")
        Role.objects.filter(id=deleted.id).update(validity_to="2020-01-01")
        create_test_officer(custom_props={"code": "RAEO01", "last_name": "RowArgsOfficer"})
        deleted = create_test_officer(custom_props={"code": "RAEO02", "last_name": "RowArgsOfficer"})
        Officer.objects.filter(id=deleted.id).update(validity_to="2020-01-01")
        create_test_claim_admin(custom_props={"code": "RACA01", "last_name": "RowArgsAdmin"})
        deleted = create_test_claim_admin(custom_props={"code": "RACA02", "last_name": "RowArgsAdmin"})
        ClaimAdmin.objects.filter(id=deleted.id).update(validity_to="2020-01-01")

    def _values(self, field, args, attr):
        response = self.query(
            '{ %s(%s) { edges { node { %s } } } }' % (field, args, attr),
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.token}"})
        self.assertResponseNoErrors(response)
        return sorted(e["node"][attr] for e in json.loads(response.content)["data"][field]["edges"])

    def test_role_default_hides_deleted(self):
        self.assertEqual(["RowArgsRole live"], self._values("role", 'str: "RowArgsRole"', "name"))

    def test_role_show_history_keeps_its_legacy_meaning(self):
        self.assertEqual(["RowArgsRole deleted", "RowArgsRole live"],
                         self._values("role", 'str: "RowArgsRole", showHistory: true', "name"))

    def test_role_is_deleted(self):
        self.assertEqual(["RowArgsRole deleted"],
                         self._values("role", 'str: "RowArgsRole", isDeleted: true', "name"))
        self.assertEqual(["RowArgsRole live"],
                         self._values("role", 'str: "RowArgsRole", showHistory: true, isDeleted: false', "name"))

    def test_enrolment_officers_default_hides_deleted(self):
        self.assertEqual(["RAEO01"], self._values("enrolmentOfficers", 'str: "RowArgsOfficer"', "code"))
        self.assertEqual(["RAEO02"],
                         self._values("enrolmentOfficers", 'str: "RowArgsOfficer", isDeleted: true', "code"))

    def test_claim_admins(self):
        self.assertEqual(["RACA01"], self._values("claimAdmins", 'search: "RowArgsAdmin"', "code"))
        self.assertEqual(["RACA02"],
                         self._values("claimAdmins", 'search: "RowArgsAdmin", isDeleted: true', "code"))
