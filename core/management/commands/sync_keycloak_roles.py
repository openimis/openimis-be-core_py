import os
import requests
import time
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from core.models import InteractiveUser, UserRole, Role
from core.keycloak_sync import get_admin_token, get_kc_user_id, get_openimis_roles_keycloak


class Command(BaseCommand):
    help = 'Sync Keycloak user attribute openimis_roles -> OpenIMIS tblUserRole'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Login name of the single user to sync')
        parser.add_argument('--realm', type=str, default=getattr(settings, 'KEYCLOAK_REALM', 'openimis'), help='Keycloak realm')
        parser.add_argument('--dry-run', action='store_true', help='Do not perform DB writes, only show what would be done')

    def handle(self, *args, **options):
        username = options.get('user')
        realm = options.get('realm')
        dry_run = options.get('dry_run')

        if username:
            users_qs = InteractiveUser.objects.filter(login_name=username, validity_to__isnull=True)
        else:
            users_qs = InteractiveUser.objects.filter(validity_to__isnull=True)

        total = users_qs.count()
        self.stdout.write(f'Found {total} OpenIMIS users to process')

        if not dry_run:
            try:
                admin_token = get_admin_token()
            except Exception as e:
                raise CommandError(f'Failed to get Keycloak admin token: {e}')
        else:
            admin_token = None

        base = os.environ.get('KEYCLOAK_BASE', getattr(settings, 'KEYCLOAK_SERVER_URL', 'http://localhost:8080'))

        processed = 0
        errors = 0

        for iuser in users_qs.iterator():
            try:
                uid = iuser.login_name
                self.stdout.write(f'Processing {uid}...')
                if dry_run:
                    processed += 1
                    continue

                user_id = get_kc_user_id(admin_token, base, realm, uid)
                if not user_id:
                    self.stderr.write(f'Keycloak user not found for {uid} - skipping')
                    errors += 1
                    continue

                kc_roles = get_openimis_roles_keycloak(admin_token, base, realm, user_id) or []
                kc_roles_set = set(kc_roles)

                # Add missing roles
                for role_name in kc_roles:
                    try:
                        role_obj = Role.objects.get(name=role_name)
                        if not UserRole.objects.filter(user=iuser, role=role_obj).exists():
                            UserRole.objects.create(user=iuser, role=role_obj)
                            self.stdout.write(f'  ADDED role {role_name} to {uid}')
                    except Role.DoesNotExist:
                        self.stdout.write(f'  KC role {role_name} not found in DB')

                # Remove roles present in DB but not in Keycloak
                db_roles = UserRole.objects.filter(user=iuser)
                for ur in db_roles:
                    if ur.role.name not in kc_roles_set:
                        self.stdout.write(f'  REMOVING role {ur.role.name} from {uid}')
                        ur.delete()

                # Invalidate rights cache if present
                try:
                    from django.core.cache import cache
                    cache.delete(f'rights_{iuser.id}')
                except Exception:
                    pass

                processed += 1
                time.sleep(0.02)

            except Exception as e:
                self.stderr.write(f'Error processing {getattr(iuser, "login_name", iuser)}: {e}')
                errors += 1

        self.stdout.write(f'Done. Processed: {processed}, Errors: {errors}')
