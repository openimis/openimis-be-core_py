"""The before_mutating receivers share the transaction of the mutation.

Modules connect receivers to a module's before_mutating signal to cascade a
mutation into their own data (contribution and payment cascade a policy
deletion into premiums and payments). The signal used to be sent before the
mutation checked the caller's rights, outside its transaction, so a refused
mutation still left the cascade behind. Now a mutation that raises or returns
errors rolls back what the receivers did, on the synchronous path and in the
async worker, and the request that queues an async job sends nothing itself.
"""

import json
import uuid
from unittest.mock import patch

import core
from core.models import Language, MutationLog, Role
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.schema import CreateRoleMutation, signal_mutation_module_before_mutating
from core.tasks import openimis_mutation_async
from core.test_helpers import create_test_interactive_user

CREATE_ROLE = """
mutation ($input: CreateRoleMutationInput!) {
  createRole(input: $input) {
    clientMutationId
    internalId
  }
}
"""


def _marker_code():
    # Language.code is at most 5 characters.
    return "z" + uuid.uuid4().hex[:4]


class BeforeMutatingTransactionTest(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = create_test_interactive_user(username="bm_tx_admin")
        cls.admin_token = BaseTestContext(user=cls.admin).get_jwt()
        cls.no_rights = create_test_interactive_user(
            username="bm_tx_norights", roles=[], custom_props={"is_superuser": False}
        )
        cls.no_rights_token = BaseTestContext(user=cls.no_rights).get_jwt()

    def setUp(self):
        super().setUp()
        self.calls = []
        self.marker = _marker_code()
        signal_mutation_module_before_mutating["core"].connect(
            self._receiver, sender=CreateRoleMutation, weak=False
        )

    def tearDown(self):
        signal_mutation_module_before_mutating["core"].disconnect(
            self._receiver, sender=CreateRoleMutation
        )
        super().tearDown()

    def _receiver(self, sender, **kwargs):
        # Stands for a cascade such as "delete the premiums of these policies".
        self.calls.append(kwargs)
        Language.objects.create(code=self.marker, name="before mutating marker")
        return []

    def _create_role(self, token, name):
        return self.query(
            CREATE_ROLE,
            variables={
                "input": {
                    "name": name,
                    "isSystem": False,
                    "isBlocked": False,
                    "clientMutationId": str(uuid.uuid4()),
                }
            },
            headers={"HTTP_AUTHORIZATION": f"Bearer {token}"},
        )

    def _queue_log(self, user, name):
        return MutationLog.objects.create(
            json_content=json.dumps({"name": name, "is_system": False, "is_blocked": False}),
            user_id=user.id,
        )

    def test_refused_mutation_rolls_back_the_receiver_changes(self):
        name = f"BmTx{uuid.uuid4().hex[:8]}"

        self._create_role(self.no_rights_token, name)

        self.assertEqual(1, len(self.calls), "the receiver must still run")
        self.assertFalse(Language.objects.filter(code=self.marker).exists())
        self.assertFalse(Role.objects.filter(name=name).exists())
        log = MutationLog.objects.get(id=self.calls[0]["mutation_log_id"])
        self.assertEqual(MutationLog.ERROR, log.status)

    def test_successful_mutation_keeps_the_receiver_changes(self):
        name = f"BmTx{uuid.uuid4().hex[:8]}"

        self._create_role(self.admin_token, name)

        self.assertEqual(1, len(self.calls))
        self.assertTrue(Language.objects.filter(code=self.marker).exists())
        self.assertTrue(Role.objects.filter(name=name).exists())

    def test_receiver_gets_the_usual_arguments(self):
        name = f"BmTx{uuid.uuid4().hex[:8]}"

        self._create_role(self.admin_token, name)

        call = self.calls[0]
        self.assertEqual("core", call["mutation_module"])
        self.assertEqual("CreateRoleMutation", call["mutation_class"])
        self.assertEqual(self.admin.id, call["user"].id)
        self.assertEqual(name, call["data"]["name"])
        self.assertTrue(MutationLog.objects.filter(id=call["mutation_log_id"]).exists())

    def test_queuing_an_async_mutation_sends_no_before_mutating_signal(self):
        with patch.object(core, "async_mutations", True), patch(
            "core.schema.openimis_mutation_async"
        ) as task:
            self._create_role(self.no_rights_token, f"BmTx{uuid.uuid4().hex[:8]}")

        self.assertTrue(task.delay.called)
        self.assertEqual([], self.calls)
        self.assertFalse(Language.objects.filter(code=self.marker).exists())

    def test_async_worker_rolls_back_the_receiver_changes_of_a_refused_mutation(self):
        name = f"BmTx{uuid.uuid4().hex[:8]}"
        log = self._queue_log(self.no_rights, name)

        openimis_mutation_async(log.id, "core", "CreateRoleMutation")

        log.refresh_from_db()
        self.assertEqual(MutationLog.ERROR, log.status)
        self.assertEqual(1, len(self.calls), "the worker must send the signal")
        self.assertEqual(log.id, self.calls[0]["mutation_log_id"])
        self.assertFalse(Language.objects.filter(code=self.marker).exists())
        self.assertFalse(Role.objects.filter(name=name).exists())

    def test_async_worker_keeps_the_receiver_changes_of_a_successful_mutation(self):
        name = f"BmTx{uuid.uuid4().hex[:8]}"
        log = self._queue_log(self.admin, name)

        openimis_mutation_async(log.id, "core", "CreateRoleMutation")

        log.refresh_from_db()
        self.assertEqual(MutationLog.SUCCESS, log.status, log.error)
        self.assertTrue(Language.objects.filter(code=self.marker).exists())
        self.assertTrue(Role.objects.filter(name=name).exists())
