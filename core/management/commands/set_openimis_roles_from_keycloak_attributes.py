import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.cache import cache

from core.models import InteractiveUser, UserRole, Role, User
from core.keycloak_sync import get_admin_token, get_kc_user_id, get_openimis_roles_keycloak


def provision_user_from_keycloak(username):
    """Create minimal InteractiveUser and core.User with safe defaults.
    Mirrors the provisioning in the legacy script.
    """
    from core.models import Language

    mapping = getattr(settings, 'KEYCLOAK_USER_MAPPING', {})
    # Best-effort defaults
    email = f"{username}@example.com"
    last_name = username
    other_names = username

    language = Language.objects.first()
    if not language:
        raise RuntimeError('No Language found in DB to create InteractiveUser')

    audit_user_id = getattr(settings, 'AUTO_PROVISION_AUDIT_USER_ID', 2)
    role_id = getattr(settings, 'AUTO_PROVISION_ROLE_ID', None)

    i_user = InteractiveUser(
        login_name=username,
        last_name=last_name,
        other_names=other_names,
        email=email,
        language=language,
        audit_user_id=audit_user_id,
    )
    if role_id is not None:
        i_user.role_id = role_id
    i_user.save()

    user = User.objects.create(username=username, i_user=i_user)
    return i_user, user


class Command(BaseCommand):
    help = 'Set OpenIMIS UserRole from Keycloak user attribute openimis_roles (inverse sync)'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Login name of the single user to sync')
        parser.add_argument('--realm', type=str, default=getattr(settings, 'KEYCLOAK_REALM', 'openimis'), help='Target Keycloak realm')
        parser.add_argument('--create-users', action='store_true', help='If user not present in OpenIMIS but present in Keycloak, create the OpenIMIS user')
        parser.add_argument('--dry-run', action='store_true', help='Do not write to DB, only show intended changes')

    def handle(self, *args, **options):
        username = options.get('user')
        realm = options.get('realm')
        create_users = options.get('create_users')
        dry_run = options.get('dry_run')

        users_qs = None
        if username:
            users_qs = InteractiveUser.objects.filter(login_name=username, validity_to__isnull=True)
            if not users_qs.exists():
                if create_users:
                    # Check Keycloak for existence; if exists, provision
                    try:
                        token = get_admin_token()
                    except Exception as e:
                        raise CommandError(f'Cannot get Keycloak admin token: {e}')

                    KEYCLOAK_BASE = os.environ.get('KEYCLOAK_BASE', getattr(settings, 'KEYCLOAK_SERVER_URL', 'http://localhost:8080'))
                    kc_id = get_kc_user_id(token, KEYCLOAK_BASE, realm, username)
                    if kc_id:
                        if dry_run:
                            self.stdout.write(self.style.WARNING(f'[DRY RUN] Would create OpenIMIS user for {username}'))
                            users_qs = InteractiveUser.objects.filter(login_name=username)  # empty
                        else:
                            self.stdout.write(f'Provisioning OpenIMIS user for {username} (from Keycloak)')
                            i_user, core_user = provision_user_from_keycloak(username)
                            users_qs = InteractiveUser.objects.filter(id=i_user.id)
                    else:
                        raise CommandError(f'User {username} not found in OpenIMIS and not present in Keycloak')
                else:
                    raise CommandError(f'User {username} not found in OpenIMIS (use --create-users to provision from Keycloak)')
        else:
            users_qs = InteractiveUser.objects.filter(validity_to__isnull=True)

        if not dry_run:
            try:
                admin_token = get_admin_token()
            except Exception as e:
                raise CommandError(f'Cannot get Keycloak admin token: {e}')
        else:
            admin_token = None

        KEYCLOAK_BASE = os.environ.get('KEYCLOAK_BASE', getattr(settings, 'KEYCLOAK_SERVER_URL', 'http://localhost:8080'))

        processed = 0
        errors = 0

        for iuser in users_qs.iterator():
            try:
                username = iuser.login_name
                self.stdout.write(f'Processing {username}')

                # Find Keycloak user
                if admin_token:
                    user_id = get_kc_user_id(admin_token, KEYCLOAK_BASE, realm, username)
                else:
                    user_id = None

                if not user_id:
                    self.stdout.write(self.style.WARNING(f'Keycloak user not found for {username} - skipping'))
                    errors += 1
                    continue

                kc_roles = get_openimis_roles_keycloak(admin_token, KEYCLOAK_BASE, realm, user_id) or []
                kc_set = set(kc_roles)
                self.stdout.write(f' Keycloak openimis_roles: {kc_roles}')

                # Add missing roles from Keycloak into DB
                for role_name in kc_roles:
                    try:
                        role_obj = Role.objects.get(name=role_name)
                        if not UserRole.objects.filter(user=iuser, role=role_obj).exists():
                            if dry_run:
                                self.stdout.write(self.style.WARNING(f'  [DRY RUN] Would add role {role_name} to {username}'))
                            else:
                                UserRole.objects.create(user=iuser, role=role_obj)
                                self.stdout.write(f'  Added role {role_name} to {username}')
                        else:
                            self.stdout.write(f'  Role {role_name} already present')
                    except Role.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f'  Role {role_name} not found in DB'))

                # Remove roles present in DB but not in Keycloak
                db_roles = UserRole.objects.filter(user=iuser)
                for ur in db_roles:
                    if ur.role.name not in kc_set:
                        if dry_run:
                            self.stdout.write(self.style.WARNING(f'  [DRY RUN] Would remove role {ur.role.name} from {username}'))
                        else:
                            self.stdout.write(f'  Removing role {ur.role.name} from {username}')
                            ur.delete()

                # Invalidate rights cache used by runtime
                try:
                    cache.delete(f'rights_{iuser.id}')
                except Exception:
                    pass

                processed += 1

            except Exception as e:
                self.stderr.write(f'Error processing {getattr(iuser, "login_name", iuser)}: {e}')
                errors += 1

        self.stdout.write(f'Done. Processed: {processed}, Errors: {errors}')
