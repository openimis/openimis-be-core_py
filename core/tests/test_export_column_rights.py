"""
OP-3353 / CVE-2026-82491: `individualExport` columns may only follow relations the caller
is allowed to read.

The export used to hand the requested columns straight to ``values_list``, so a column
such as ``userCreated.iUser.password`` put the creator's password hash into the CSV.
These tests go through GraphQL and read the file the export wrote.
"""

import io
import json

import pandas as pd

from core.models import ExportableQueryModel
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import create_admin_role, create_test_interactive_user


class ExportColumnRightsGQLTestCase(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from individual.models import Individual

        cls.admin_user = create_test_interactive_user(
            username="op3353ExportAdmin", roles=[create_admin_role().id]
        )
        cls.admin_token = BaseTestContext(user=cls.admin_user).get_jwt()
        cls.individual = Individual(
            first_name="Op3353First",
            last_name="Op3353Last",
            dob="1990-01-01",
            json_ext={"educated_level": "primary"},
        )
        cls.individual.save(username=cls.admin_user.username)

    def _export(self, fields, columns=None):
        before = set(
            ExportableQueryModel.objects.filter(user=self.admin_user).values_list(
                "id", flat=True
            )
        )
        query = """
            query ($fields: [String], $columns: GenericScalar) {
              individualExport(firstName_Iexact: "Op3353First", fields: $fields, fieldsColumns: $columns)
            }
        """
        response = self.query(
            query,
            variables={"fields": fields, "columns": json.dumps(columns or {})},
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
        )
        self.assertResponseNoErrors(response)
        export = (
            ExportableQueryModel.objects.filter(user=self.admin_user)
            .exclude(id__in=before)
            .get()
        )
        export.content.open("rb")
        try:
            return export.content.read().decode()
        finally:
            export.content.close()

    def test_creator_password_hash_is_never_exported(self):
        password_hash = self.admin_user.i_user.password
        self.assertTrue(password_hash)
        content = self._export(["id", "firstName", "userCreated.iUser.password"])
        self.assertNotIn(password_hash, content)
        self.assertNotIn("user_created__i_user__password", content)

    def test_column_through_a_model_without_a_right_is_dropped(self):
        content = self._export(["id", "userCreated.username"])
        self.assertNotIn("user_created__username", content)
        self.assertNotIn(self.admin_user.username, content)

    def test_columns_the_ui_sends_are_still_exported(self):
        content = self._export(
            ["id", "first_name", "last_name", "dob", "json_ext"],
            columns={"first_name": "First name"},
        )
        frame = pd.read_csv(io.StringIO(content))
        self.assertIn("First name", frame.columns)
        self.assertIn("last_name", frame.columns)
        self.assertEqual(list(frame["First name"]), ["Op3353First"])
        self.assertIn("primary", content)

    def test_export_with_only_refused_columns_fails_rather_than_exporting_everything(self):
        """`values_list()` with no column returns every column of the root model."""
        response = self.query(
            """
            query ($fields: [String], $columns: GenericScalar) {
              individualExport(firstName_Iexact: "Op3353First", fields: $fields, fieldsColumns: $columns)
            }
            """,
            variables={"fields": ["userCreated.iUser.password"], "columns": "{}"},
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
        )
        content = json.loads(response.content)
        self.assertIn("errors", content)
        self.assertIsNone(content["data"]["individualExport"])
