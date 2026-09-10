import sys
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError, ProgrammingError
from django.test import TestCase

from core import bootstrap


class BootstrapModeTestCase(TestCase):
    """The predicates that say whether the database can be relied on."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(bootstrap, "_schema_available", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_database_mode_reads_the_env_variable(self):
        for value, expected in (
            ("True", True),
            ("true", True),
            ("1", True),
            ("False", False),
            ("0", False),
            ("", False),
        ):
            with self.subTest(value=value), mock.patch.dict(
                "os.environ", {"NO_DATABASE": value}
            ):
                self.assertEqual(bootstrap.no_database_mode(), expected)

    def test_no_database_mode_defaults_to_false(self):
        with mock.patch.dict("os.environ", clear=False) as environ:
            environ.pop("NO_DATABASE", None)
            self.assertFalse(bootstrap.no_database_mode())

    def test_migration_commands_are_recognised(self):
        for argv, expected in (
            (["manage.py", "migrate"], True),
            (["manage.py", "makemigrations", "core"], True),
            (["manage.py", "runserver"], False),
            (["manage.py"], False),
        ):
            with self.subTest(argv=argv), mock.patch.object(sys, "argv", argv):
                self.assertEqual(bootstrap.running_migration_command(), expected)

    def test_database_is_not_expected_during_a_migration(self):
        with mock.patch.object(sys, "argv", ["manage.py", "migrate"]):
            self.assertFalse(bootstrap.database_expected())
            self.assertEqual(bootstrap.unavailability_reason(), "running migrate")

    def test_database_is_expected_once_migrations_have_run(self):
        with mock.patch.object(sys, "argv", ["manage.py", "migrate"]):
            bootstrap.mark_schema_available()
            self.assertTrue(bootstrap.database_expected())

    def test_no_database_wins_over_an_applied_schema(self):
        with mock.patch.dict("os.environ", {"NO_DATABASE": "True"}):
            bootstrap.mark_schema_available()
            self.assertFalse(bootstrap.database_expected())
            self.assertEqual(bootstrap.unavailability_reason(), "NO_DATABASE is set")


class OptionalDatabaseTestCase(TestCase):
    def test_the_block_runs_when_nothing_goes_wrong(self):
        ran = []
        with bootstrap.optional_database("something"):
            ran.append(True)
        self.assertEqual(ran, [True])

    def test_a_missing_table_does_not_propagate(self):
        for error in (
            ProgrammingError("relation does not exist"),
            OperationalError("connection refused"),
            ImproperlyConfigured("no database configured"),
        ):
            with self.subTest(error=type(error).__name__):
                with bootstrap.optional_database("something"):
                    raise error

    def test_later_blocks_still_run_after_a_failure(self):
        ran = []
        with bootstrap.optional_database("first"):
            raise OperationalError("connection refused")
        with bootstrap.optional_database("second"):
            ran.append("second")
        self.assertEqual(ran, ["second"])

    def test_unrelated_errors_still_propagate(self):
        with self.assertRaises(ValueError):
            with bootstrap.optional_database("something"):
                raise ValueError("a real bug")

    def test_tolerate_all_swallows_unrelated_errors(self):
        with bootstrap.optional_database("something", tolerate_all=True):
            raise ValueError("a real bug")


class SkipWithoutDatabaseTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.calls = []

        @bootstrap.skip_without_database("some database work")
        def work():
            self.calls.append(True)
            return "done"

        self.work = work

    def test_runs_when_the_database_is_expected(self):
        with mock.patch.object(bootstrap, "database_expected", return_value=True):
            self.assertEqual(self.work(), "done")
        self.assertEqual(len(self.calls), 1)

    def test_skipped_when_the_database_is_not_expected(self):
        with mock.patch.object(bootstrap, "database_expected", return_value=False):
            self.assertIsNone(self.work())
        self.assertEqual(self.calls, [])

    def test_a_database_failure_is_swallowed(self):
        @bootstrap.skip_without_database("failing work")
        def failing():
            raise OperationalError("connection refused")

        with mock.patch.object(bootstrap, "database_expected", return_value=True):
            self.assertIsNone(failing())


class RerunAfterMigrateTestCase(TestCase):
    """The post_migrate retry, without dragging in every other receiver."""

    def _connect(self, callback):
        """Return the handler rerun_after_migrate would wire to post_migrate."""
        sender = mock.Mock()
        with mock.patch("django.db.models.signals.post_migrate.connect") as connect:
            bootstrap.rerun_after_migrate(sender, callback, "core.test_rerun")
        connect.assert_called_once()
        self.assertEqual(connect.call_args.kwargs["sender"], sender)
        self.assertEqual(connect.call_args.kwargs["dispatch_uid"], "core.test_rerun")
        # a lambda handler would be garbage collected straight away
        self.assertFalse(connect.call_args.kwargs["weak"])
        return connect.call_args.args[0]

    def test_the_callback_runs_and_is_not_skipped_as_a_migration(self):
        seen = []
        handler = self._connect(lambda: seen.append(bootstrap.database_expected()))

        with mock.patch.object(bootstrap, "_schema_available", False), \
                mock.patch.object(sys, "argv", ["manage.py", "migrate"]):
            handler(sender=mock.Mock())

        # the schema exists by then, so the callback must not consider itself
        # to be running without a database
        self.assertEqual(seen, [True])
