import os
from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create a superuser for openIMIS using the core.User create_superuser implementation. "
        "Supports --password for non-interactive use (e.g. scripts, Docker, CI)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            dest="username",
            default=None,
            help="Specifies the login name for the superuser.",
        )
        parser.add_argument(
            "--password",
            dest="password",
            default=None,
            help="Specifies the password for the superuser (enables non-interactive creation).",
        )
        parser.add_argument(
            "--email",
            dest="email",
            default="",
            help="Specifies the email address for the superuser.",
        )
        parser.add_argument(
            "--last-name",
            dest="last_name",
            default="Admin",
            help="Specifies the LastName for the underlying InteractiveUser (default: Admin).",
        )
        parser.add_argument(
            "--other-names",
            dest="other_names",
            default="Super",
            help="Specifies the OtherNames for the underlying InteractiveUser (default: Super).",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Do not prompt the user for input of any kind. "
                 "Username and password must be provided via options or DJANGO_SUPERUSER_* env vars.",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        username = options.get("username")
        password = options.get("password")
        email = options.get("email") or None
        last_name = options.get("last_name") or "Admin"
        other_names = options.get("other_names") or "Super"
        interactive = options.get("interactive", True)

        if not username:
            if interactive:
                username = input("Username: ").strip()
            else:
                raise CommandError("--username is required when using --noinput.")

        if not username:
            raise CommandError("Username cannot be empty.")

        if not password:
            env_pw = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
            if env_pw:
                password = env_pw
            elif interactive:
                password = getpass("Password: ")
                password2 = getpass("Password (again): ")
                if password != password2:
                    raise CommandError("Passwords do not match.")
            else:
                raise CommandError(
                    "You must provide --password or set DJANGO_SUPERUSER_PASSWORD when using --noinput."
                )

        if not password:
            raise CommandError("Password cannot be empty.")

        try:
            user = User.objects.create_superuser(
                username=username,
                password=password,
                email=email,
                last_name=last_name,
                other_names=other_names,
            )
        except Exception as exc:
            raise CommandError(f"Failed to create superuser: {exc}")

        self.stdout.write(
            self.style.SUCCESS(f"Superuser '{username}' created successfully (id={user.pk}).")
        )
