"""Helpers for start-up code that runs before the database is guaranteed usable.

``AppConfig.ready()`` runs for *every* management command, including the ones
that build the schema (``migrate``, ``makemigrations``) and the ones meant to
run without a real database at all (``NO_DATABASE=True``). Start-up code can
therefore not assume a reachable connection, an existing database or
up-to-date tables.

Wrap such work in :func:`optional_database` so that a missing server, database
or table degrades to a log line instead of aborting the whole process::

    with optional_database("create the auto provisioning group"):
        Group.objects.get_or_create(name=group)

    # runs even if the block above was skipped
    with optional_database("grant view_user to the auto provisioning group"):
        ...

Each block is independent: a failure in one does not prevent the next from
running. Only errors meaning "the database is not usable" are swallowed;
anything else (a bug in the block, a validation error) still propagates.

Catching the error is not always enough. When the database is known not to be
there -- ``NO_DATABASE=True``, or a ``migrate`` that has yet to create the
tables -- the attempt itself is the problem: connecting to a host that is not
answering blocks until the driver gives up, which can stall start-up for
minutes. Skip the work outright in that case, either with
:func:`skip_without_database` on a function that is nothing but database work,
or with a :func:`database_expected` check where only part of the work has to
go.

Do not use these inside an ``atomic()`` block: swallowing a database error
there leaves the transaction unusable for the rest of the block.
"""

import logging
import os
import sys
from contextlib import contextmanager
from functools import wraps

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, InterfaceError
from django.db.utils import ConnectionDoesNotExist

logger = logging.getLogger(__name__)

# Commands that build or inspect the schema: the tables start-up code wants may
# not exist yet, or may be halfway through an upgrade.
MIGRATION_COMMANDS = frozenset(
    {
        "migrate",
        "makemigrations",
        "showmigrations",
        "sqlmigrate",
        "squashmigrations",
    }
)

# Raised when the server is unreachable, the database or table is missing, or no
# connection is configured at all. DatabaseError covers OperationalError,
# ProgrammingError and InternalError.
DATABASE_UNAVAILABLE_ERRORS = (
    DatabaseError,
    InterfaceError,
    ConnectionDoesNotExist,
    ImproperlyConfigured,
)

_FALSE_VALUES = ("", "false", "0", "no", "off")


def no_database_mode():
    """True when the process was started with the NO_DATABASE env variable set."""
    return os.environ.get("NO_DATABASE", "False").strip().lower() not in _FALSE_VALUES


def running_migration_command():
    """True when the process was started by a schema-migration command."""
    return len(sys.argv) > 1 and sys.argv[1] in MIGRATION_COMMANDS


# Set once post_migrate has fired: from then on the schema exists, even though
# argv still says this process is a migration command.
_schema_available = False


def mark_schema_available():
    """Record that migrations have been applied in this process."""
    global _schema_available
    _schema_available = True


def database_expected():
    """False when this process is known not to have a usable schema (yet).

    Use it to skip work outright when attempting the connection is itself a
    problem, and to decide how loudly to report the skip. It is a best-effort
    hint, not a guarantee: the database can always be unreachable for other
    reasons, which is why the work itself still belongs in
    :func:`optional_database`.
    """
    if no_database_mode():
        return False
    return _schema_available or not running_migration_command()


def unavailability_reason():
    """Short explanation of why the database is not expected to be usable."""
    if no_database_mode():
        return "NO_DATABASE is set"
    if running_migration_command() and not _schema_available:
        return "running %s" % sys.argv[1]
    return "database unavailable"


@contextmanager
def optional_database(action, log=None, tolerate_all=False):
    """Run database work that must not break start-up.

    :param action: what the block does, used in the log message ("create the
        auto provisioning group").
    :param log: logger to report on, defaults to this module's logger. Pass the
        caller's logger to keep the message under its own name.
    :param tolerate_all: also swallow errors unrelated to database
        availability. Only for best-effort work that must never break
        start-up; it hides real bugs, so prefer the default.

    The block always runs -- a context manager cannot skip its own body. Guard
    it with :func:`database_expected` (or use :func:`skip_without_database`)
    when even attempting the connection is a problem.
    """
    log = log or logger
    tolerated = Exception if tolerate_all else DATABASE_UNAVAILABLE_ERRORS
    try:
        yield
    except tolerated as exc:
        if database_expected():
            log.warning("Skipped %s: %s: %s", action, type(exc).__name__, exc)
        else:
            log.info("Skipped %s: %s", action, unavailability_reason())
        # one traceback per skipped step drowns the start-up log, so keep it
        # out of the way until someone is actually debugging
        log.debug("Skipped %s", action, exc_info=True)


def skip_without_database(action, log=None, tolerate_all=False):
    """Decorate a function that is nothing but database work.

    Skips the call entirely when the database is known not to be usable, and
    tolerates a database failure the rest of the time. Returns ``None`` when
    the call is skipped or failed, so only use it where the caller does not
    need a result.

    Arguments are those of :func:`optional_database`.
    """

    def decorate(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            report = log or logger
            if not database_expected():
                report.info("Skipped %s: %s", action, unavailability_reason())
                return None
            with optional_database(action, report, tolerate_all):
                return func(*args, **kwargs)
            return None

        return wrapper

    return decorate


def rerun_after_migrate(app_config, callback, dispatch_uid):
    """Run `callback` again once `app_config`'s migrations have been applied.

    ``ready()`` runs before migrations, so on a fresh database start-up work
    that needs a table finds nothing to work with. Connecting it to
    ``post_migrate`` gives it a second chance as soon as the schema exists.

    :param dispatch_uid: unique per call site, so repeated ``ready()`` calls
        (autoreloader, tests) do not stack up handlers.
    """
    from django.db.models.signals import post_migrate

    def _handler(sender, **kwargs):
        # the schema exists now, so the callback must not be skipped for being
        # in the middle of a migration command
        mark_schema_available()
        callback()

    post_migrate.connect(
        _handler, sender=app_config, dispatch_uid=dispatch_uid, weak=False
    )
