import json
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from core.models import Language, User
from core.models.base_mutation import MutationLog
from core.mutation_log_secrets import MASK, contains_secret, scrub_secrets
from core.tasks import openimis_mutation_async
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import create_admin_role, create_test_interactive_user
from core.user_types import UT_INTERACTIVE
from location.models import Location


class MutationLogSecretsTestCase(openIMISGraphQLTestCase):
    admin_username = "AdminMutLogSecrets"
    admin_password = "EdfmD3!12@#"

    CREATE_USER = """
        mutation ($input: CreateUserMutationInput!) {
            createUser(input: $input) { clientMutationId internalId }
        }
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(
            username=cls.admin_username, password=cls.admin_password
        )
        cls.admin_token = BaseTestContext(user=cls.admin_user).get_jwt()
        cls.district = Location.objects.filter(
            type="D", *Location.filter_validity()
        ).first()
        Language.objects.get_or_create(
            code="en", defaults={"name": "English", "sort_order": 2}
        )

    def _create_user_variables(self, username, secret, client_mutation_id):
        return {
            "input": {
                "uuid": None,
                "username": username,
                "userTypes": [UT_INTERACTIVE],
                "lastName": "log",
                "otherNames": "secrets",
                "email": f"{username.lower()}@openimis.org",
                "password": secret,
                "healthFacilityId": None,
                "districts": [self.district.id],
                "locationId": None,
                "language": "en",
                "roles": [create_admin_role().id],
                "substitutionOfficerId": None,
                "clientMutationLabel": "Create user",
                "clientMutationId": client_mutation_id,
            }
        }

    def test_the_response_to_the_frontend_carries_no_password(self):
        """The front end receives the input echoed back in `metadata`.

        The response travels through access logs, proxies and error reporters:
        it must not replay the password the front end has just sent.
        """
        secret = "pR3sp0nse!N0!Leak"
        client_mutation_id = "2f0f2a3c-9a1e-4f0f-9b1a-000000000003"
        query = """
            mutation ($input: CreateUserMutationInput!) {
                createUser(input: $input) {
                    clientMutationId internalId metadata
                }
            }
        """
        response = self.query(
            query,
            variables=self._create_user_variables(
                "MLS003", secret, client_mutation_id
            ),
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
        )
        self.assertResponseNoErrors(response)

        body = response.content.decode()
        self.assertNotIn(
            secret, body, "the password must not come back to the front end"
        )
        metadata = response.json()["data"]["createUser"]["metadata"]
        self.assertEqual(metadata.get("password"), MASK)
        self.assertEqual(metadata.get("username"), "MLS003")

    def test_a_secret_bearing_mutation_runs_synchronously(self):
        """The secret must reach neither the database nor the message broker.

        In async mode the log row *is* the payload `core.tasks` replays, so it
        could not be written masked. The rule is therefore to run synchronously
        any mutation whose input carries a secret: the payload then comes from
        the in-memory `data`, and the row can be written already masked. This
        test forces async mode to check that the rule does take precedence.
        """
        import core as core_module

        secret = "pF0rc3d!Syncr0n0us"
        client_mutation_id = "2f0f2a3c-9a1e-4f0f-9b1a-000000000004"
        previous = core_module.async_mutations
        core_module.async_mutations = True
        try:
            response = self.query(
                self.CREATE_USER,
                variables=self._create_user_variables(
                    "MLS004", secret, client_mutation_id
                ),
                headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
            )
            self.assertResponseNoErrors(response)
        finally:
            core_module.async_mutations = previous

        log = MutationLog.objects.filter(
            client_mutation_id=client_mutation_id
        ).first()
        self.assertIsNotNone(log)
        # ran straight away despite `async_mutations = True`
        self.assertEqual(
            log.status,
            MutationLog.SUCCESS,
            f"the mutation had to run synchronously, error: {log.error}",
        )
        # ... and the row never carried the secret
        self.assertNotIn(secret, log.json_content)
        self.assertEqual(json.loads(log.json_content)["password"], MASK)
        created = User.objects.filter(username="MLS004").first()
        self.assertIsNotNone(created)
        self.assertTrue(
            created.check_password(secret),
            "the real password must have been applied",
        )

    def test_create_user_password_is_not_kept_in_the_mutation_log(self):
        secret = "pS3cr3t!Never!Logged"
        client_mutation_id = "2f0f2a3c-9a1e-4f0f-9b1a-000000000001"
        variables = {
            "input": {
                "uuid": None,
                "username": "MLS001",
                "userTypes": [UT_INTERACTIVE],
                "lastName": "log",
                "otherNames": "secrets",
                "email": "mls001@openimis.org",
                "password": secret,
                "healthFacilityId": None,
                "districts": [self.district.id],
                "locationId": None,
                "language": "en",
                "roles": [create_admin_role().id],
                "substitutionOfficerId": None,
                "clientMutationLabel": "Create user",
                "clientMutationId": client_mutation_id,
            }
        }

        response = self.query(
            self.CREATE_USER,
            variables=variables,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"},
        )
        self.assertResponseNoErrors(response)
        self.get_mutation_result(client_mutation_id, self.admin_token)

        log = MutationLog.objects.filter(
            client_mutation_id=client_mutation_id
        ).first()
        self.assertIsNotNone(log, "the mutation does have to be logged")

        self.assertNotIn(
            secret,
            log.json_content,
            "the password must not be kept in clear text in the log",
        )
        content = json.loads(log.json_content)
        self.assertEqual(
            content.get("password"),
            "********",
            "the key must stay present, masked, so the log stays readable",
        )
        # the rest of the input is kept: the log retains its audit value
        self.assertEqual(content.get("username"), "MLS001")
        self.assertEqual(content.get("email"), "mls001@openimis.org")


class MutationLogAsyncReplayTestCase(openIMISGraphQLTestCase):
    """Defence in depth: the async replay works, and masks behind itself.

    A mutation carrying a secret now runs synchronously and its row is written
    already masked - so that path should never see a secret again. This test
    covers what could get through all the same: a row written before this fix,
    or a sensitive key `contains_secret` failed to recognise on the way in. It
    checks both halves of the remaining guarantee: `openimis_mutation_async`
    does replay the payload as it stands (otherwise the user would be created
    with the literal password "********"), and the move to a terminal state
    masks the row afterwards.
    """

    admin_username = "AdminMutLogAsync"
    admin_password = "EdfmD3!12@#"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(
            username=cls.admin_username, password=cls.admin_password
        )
        cls.district = Location.objects.filter(
            type="D", *Location.filter_validity()
        ).first()
        Language.objects.get_or_create(
            code="en", defaults={"name": "English", "sort_order": 2}
        )

    def test_async_replay_uses_the_payload_then_scrubs_it(self):
        secret = "pA5ync!Repl4y!Ok"
        payload = {
            "username": "MLS002",
            "user_types": ["INTERACTIVE"],
            "last_name": "async",
            "other_names": "replay",
            "email": "mls002@openimis.org",
            "password": secret,
            "districts": [self.district.id],
            "language": "en",
            "roles": [create_admin_role().id],
            "client_mutation_label": "Create user async",
        }
        log = MutationLog.objects.create(
            json_content=json.dumps(payload),
            user_id=self.admin_user.id,
            client_mutation_label="Create user async",
        )

        openimis_mutation_async(log.id, "core", "CreateUserMutation")

        log.refresh_from_db()
        self.assertEqual(
            log.status,
            MutationLog.SUCCESS,
            f"the replay has to succeed, error: {log.error}",
        )

        created = User.objects.filter(username="MLS002").first()
        self.assertIsNotNone(created, "the user must have been created")
        self.assertTrue(
            created.check_password(secret),
            "the real password must have been used, not the mask",
        )
        self.assertFalse(created.check_password(MASK))

        self.assertNotIn(secret, log.json_content)
        self.assertEqual(json.loads(log.json_content).get("password"), MASK)


class ScrubSecretsUnitTestCase(openIMISGraphQLTestCase):
    def test_keys_are_kept_values_are_masked(self):
        self.assertEqual(
            scrub_secrets(
                {
                    "username": "u",
                    "password": "p",
                    "nested": {"apiKey": "k", "ok": 1},
                    "items": [{"secret": "s"}, {"plain": "v"}],
                }
            ),
            {
                "username": "u",
                "password": MASK,
                "nested": {"apiKey": MASK, "ok": 1},
                "items": [{"secret": MASK}, {"plain": "v"}],
            },
        )

    def test_nothing_sensitive_is_left_untouched(self):
        payload = {"a": 1, "b": [1, 2], "c": {"d": None}}
        self.assertEqual(scrub_secrets(payload), payload)


class ScrubCommandTestCase(openIMISGraphQLTestCase):
    """`scrub_mutation_log_secrets` handles the history predating the fix."""

    def _log(self, status, payload, **kwargs):
        return MutationLog.objects.create(
            json_content=json.dumps(payload), status=status, **kwargs
        )

    def test_terminal_rows_are_scrubbed_pending_ones_are_left_alone(self):
        done = self._log(MutationLog.SUCCESS, {"username": "a", "password": "old1"})
        failed = self._log(MutationLog.ERROR, {"username": "b", "apiKey": "old2"})
        # a row still queued: `core.tasks` replays the mutation from
        # `json_content`, masking it would break the mutation.
        pending = self._log(MutationLog.RECEIVED, {"username": "c", "password": "old3"})
        untouched = self._log(MutationLog.SUCCESS, {"username": "d", "age": 30})

        out = StringIO()
        call_command("scrub_mutation_log_secrets", stdout=out)

        done.refresh_from_db()
        failed.refresh_from_db()
        pending.refresh_from_db()
        untouched.refresh_from_db()

        self.assertEqual(json.loads(done.json_content)["password"], MASK)
        self.assertEqual(json.loads(failed.json_content)["apiKey"], MASK)
        self.assertEqual(
            json.loads(pending.json_content)["password"],
            "old3",
            "a mutation still pending must keep its payload",
        )
        self.assertEqual(json.loads(untouched.json_content)["age"], 30)
        # No assertion on the overall count: the test database is kept between
        # runs (--keepdb), so other rows live on in it. The per-row assertions
        # above are what has to be checked.
        self.assertIn("row(s) masked", out.getvalue())

    def test_dry_run_writes_nothing(self):
        row = self._log(MutationLog.SUCCESS, {"password": "still-here"})
        out = StringIO()
        call_command("scrub_mutation_log_secrets", "--dry-run", stdout=out)
        row.refresh_from_db()
        self.assertEqual(json.loads(row.json_content)["password"], "still-here")
        self.assertIn("nothing was written", out.getvalue())

    def test_stale_pending_rows_can_be_included(self):
        stale = self._log(MutationLog.RECEIVED, {"password": "abandoned"})
        # `request_date_time` is auto_now_add: push it back into the past.
        MutationLog.objects.filter(id=stale.id).update(
            request_date_time=timezone.now() - timezone.timedelta(hours=48)
        )
        recent = self._log(MutationLog.RECEIVED, {"password": "queued"})

        call_command(
            "scrub_mutation_log_secrets",
            "--include-pending",
            "--older-than-hours",
            "24",
            stdout=StringIO(),
        )

        stale.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual(json.loads(stale.json_content)["password"], MASK)
        self.assertEqual(
            json.loads(recent.json_content)["password"],
            "queued",
            "a recent row may still be picked up by the worker",
        )
