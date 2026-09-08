import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import Language, User


class _Tty:
    def isatty(self):
        return True


class CreateSuperuserCommandTest(TestCase):
    PASSWORD = "S/pe®Pąßw0rd™"

    def setUp(self):
        Language.objects.get_or_create(
            code="en",
            defaults={"name": "English", "sort_order": 1},
        )

    def test_command_is_served_from_core(self):
        self.assertEqual(get_commands()["createsuperuser"], "core")

    def test_noinput_uses_env_password(self):
        username = "csu_env_user"
        env = {
            "DJANGO_SUPERUSER_PASSWORD": self.PASSWORD,
        }
        out = StringIO()
        with patch.dict(os.environ, env, clear=False):
            call_command(
                "createsuperuser",
                interactive=False,
                username=username,
                stdout=out,
            )
        user = User.objects.get(username=username)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(self.PASSWORD))
        self.assertEqual(user.i_user.last_name, "Admin")
        self.assertEqual(user.i_user.other_names, "Super")
        self.assertIn("Superuser created successfully", out.getvalue())

    def test_noinput_optional_fields_and_env(self):
        username = "csu_opt_user"
        env = {
            "DJANGO_SUPERUSER_PASSWORD": self.PASSWORD,
            "DJANGO_SUPERUSER_EMAIL": "admin@example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            call_command(
                "createsuperuser",
                interactive=False,
                username=username,
                last_name="Doe",
                other_names="Jane",
                stdout=StringIO(),
            )
        user = User.objects.get(username=username)
        self.assertEqual(user.i_user.email, "admin@example.com")
        self.assertEqual(user.i_user.last_name, "Doe")
        self.assertEqual(user.i_user.other_names, "Jane")
        self.assertTrue(user.check_password(self.PASSWORD))

    def test_rejects_non_django_password_flag(self):
        with self.assertRaises(TypeError):
            call_command(
                "createsuperuser",
                interactive=False,
                username="csu_bad_flag",
                password=self.PASSWORD,
                stdout=StringIO(),
            )

    @patch(
        "django.contrib.auth.management.commands.createsuperuser.getpass.getpass",
        return_value="S/pe®Pąßw0rd™",
    )
    def test_interactive_prompts_for_password(self, _mock_getpass):
        username = "csu_interactive"
        call_command(
            "createsuperuser",
            interactive=True,
            username=username,
            stdin=_Tty(),
            stdout=StringIO(),
        )
        user = User.objects.get(username=username)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(self.PASSWORD))
        self.assertEqual(_mock_getpass.call_count, 2)

    def test_duplicate_username(self):
        username = "csu_dup"
        with patch.dict(
            os.environ, {"DJANGO_SUPERUSER_PASSWORD": self.PASSWORD}, clear=False
        ):
            call_command(
                "createsuperuser",
                interactive=False,
                username=username,
                stdout=StringIO(),
            )
            with self.assertRaises(CommandError):
                call_command(
                    "createsuperuser",
                    interactive=False,
                    username=username,
                    stdout=StringIO(),
                )
