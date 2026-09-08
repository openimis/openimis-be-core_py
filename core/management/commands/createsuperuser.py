"""
openIMIS createsuperuser.

core.User has no password field (the hash lives on InteractiveUser), so Django's
stock command skips the password prompt. This subclass keeps Django's CLI, env
vars, and interactive flow, and only forces password collection.
"""
from contextlib import contextmanager
import os

from django.contrib.auth.management.commands.createsuperuser import (
    PASSWORD_FIELD,
    Command as DjangoCreateSuperuserCommand,
)
from django.core import exceptions
from django.db import models


# Optional InteractiveUser fields. Same env-var pattern as Django REQUIRED_FIELDS
# (DJANGO_SUPERUSER_<FIELD>), but they are not required and are not prompted.
INTERACTIVE_USER_OPTIONAL_FIELDS = ("email", "last_name", "other_names")


@contextmanager
def _force_password_field(user_model):
    """Make _meta.get_field('password') succeed so Django collects a password."""
    meta = user_model._meta
    original_get_field = meta.get_field

    def get_field(field_name):
        if field_name == PASSWORD_FIELD:
            try:
                return original_get_field(field_name)
            except exceptions.FieldDoesNotExist:
                field = models.CharField(max_length=256)
                field.name = PASSWORD_FIELD
                field.attname = PASSWORD_FIELD
                return field
        return original_get_field(field_name)

    meta.get_field = get_field
    try:
        yield
    finally:
        meta.get_field = original_get_field


@contextmanager
def _inject_create_superuser_kwargs(user_model, extras):
    manager_class = type(user_model._default_manager)
    original = manager_class.create_superuser

    def wrapped(self, *args, **kwargs):
        for key, value in extras.items():
            kwargs.setdefault(key, value)
        return original(self, *args, **kwargs)

    manager_class.create_superuser = wrapped
    try:
        yield
    finally:
        manager_class.create_superuser = original


class Command(DjangoCreateSuperuserCommand):
    help = (
        "Used to create a superuser. Same options as Django's createsuperuser; "
        "the password is stored on the linked InteractiveUser."
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        existing = {action.dest for action in parser._actions}
        help_by_field = {
            "email": "Specifies the email for the superuser.",
            "last_name": (
                "Specifies the LastName for the InteractiveUser (default: Admin)."
            ),
            "other_names": (
                "Specifies the OtherNames for the InteractiveUser (default: Super)."
            ),
        }
        for name in INTERACTIVE_USER_OPTIONAL_FIELDS:
            if name not in existing:
                parser.add_argument("--%s" % name, help=help_by_field[name])

    def handle(self, *args, **options):
        extras = {}
        for name in INTERACTIVE_USER_OPTIONAL_FIELDS:
            value = options.get(name) or os.environ.get(
                "DJANGO_SUPERUSER_" + name.upper()
            )
            if value:
                extras[name] = value
        with _force_password_field(self.UserModel), _inject_create_superuser_kwargs(
            self.UserModel, extras
        ):
            return super().handle(*args, **options)
