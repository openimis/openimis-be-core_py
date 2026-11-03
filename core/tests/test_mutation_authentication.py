"""An anonymous mutation must be refused before anything is persisted or queued.

Every OpenIMISMutation requires an authenticated user, but each one checks
inside ``async_mutate`` -- which runs after the MutationLog row is written and,
when ``async_mutations`` is on (the default whenever MODE=prod), after a Celery
job has been queued for it. Without the gate in ``mutate_and_get_payload`` an
anonymous caller could make the server write a row whose content it controls and
occupy a worker, once per request and without credentials.
"""

import json
import uuid
from unittest.mock import patch

import core
from core.gql_errors import UNAUTHENTICATED
from core.models import MutationLog, Role
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.test_helpers import create_test_interactive_user

CREATE_ROLE = """
mutation ($input: CreateRoleMutationInput!) {
  createRole(input: $input) {
    clientMutationId
    internalId
  }
}
"""


def role_variables(name=None):
    return {
        "input": {
            "name": name or f"AuthGate{uuid.uuid4().hex[:8]}",
            "isSystem": False,
            "isBlocked": False,
            "clientMutationId": str(uuid.uuid4()),
        }
    }


class AnonymousMutationIsRefusedEarlyTest(openIMISGraphQLTestCase):
    def test_anonymous_mutation_returns_401(self):
        response = self.query(CREATE_ROLE, variables=role_variables())

        self.assertEqual(401, response.status_code)

    def test_anonymous_mutation_reports_the_unauthenticated_code(self):
        response = self.query(CREATE_ROLE, variables=role_variables())

        errors = json.loads(response.content)["errors"]
        codes = [error.get("extensions", {}).get("code") for error in errors]
        self.assertIn(UNAUTHENTICATED, codes)

    def test_anonymous_mutation_writes_no_mutation_log(self):
        before = MutationLog.objects.count()

        self.query(CREATE_ROLE, variables=role_variables())

        self.assertEqual(before, MutationLog.objects.count())

    def test_anonymous_mutation_queues_no_task(self):
        # async_mutations is True whenever MODE=prod, so the queue is the live
        # configuration's behaviour, not an edge case.
        with patch.object(core, "async_mutations", True), patch(
            "core.schema.openimis_mutation_async"
        ) as task:
            self.query(CREATE_ROLE, variables=role_variables())

        self.assertFalse(task.delay.called)

    def test_anonymous_mutation_creates_nothing(self):
        name = f"AuthGate{uuid.uuid4().hex[:8]}"

        self.query(CREATE_ROLE, variables=role_variables(name))

        self.assertFalse(Role.objects.filter(name=name).exists())


class AuthenticatedMutationStillLogsTest(openIMISGraphQLTestCase):
    """The gate must not swallow an authenticated caller's audit trail.

    A user who is authenticated but lacks the permission still gets a
    MutationLog row: that row is the record of a real user's denied attempt, and
    it costs credentials to create, so it is not an anonymous DoS vector.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(
            username="authgate_user", custom_props={"is_superuser": False}
        )
        cls.token = BaseTestContext(user=cls.user).get_jwt()

    def test_authenticated_mutation_is_registered(self):
        before = MutationLog.objects.count()

        response = self.query(
            CREATE_ROLE,
            variables=role_variables(),
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )

        self.assertNotEqual(401, response.status_code)
        self.assertEqual(before + 1, MutationLog.objects.count())
