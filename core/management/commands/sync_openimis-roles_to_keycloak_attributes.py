import os
import requests
import time
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.cache import cache
from core.models import InteractiveUser, UserRole, Role
from core.keycloak_sync import get_admin_token, get_kc_user_id, set_kc_openimis_roles


class Command(BaseCommand):
    help = 'Sync OpenIMIS tblUserRole -> Keycloak user attribute openimis_roles'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Login name of the single user to sync')
        parser.add_argument('--realm', type=str, default=getattr(settings, 'KEYCLOAK_REALM', 'openimis'), help='Target Keycloak realm')
        parser.add_argument('--dry-run', action='store_true', help='Do not perform writes to Keycloak, only show what would be done')

    def handle(self, *args, **options):
        username = options.get('user')
        realm = options.get('realm')
        dry_run = options.get('dry_run')

        users_qs = None
        if username:
            users_qs = InteractiveUser.objects.filter(login_name=username, validity_to__isnull=True)
        else:
            users_qs = InteractiveUser.objects.filter(validity_to__isnull=True)

        total = users_qs.count()
        self.stdout.write(f'Found {total} OpenIMIS users to process')

        if not dry_run:
            try:
                admin_token = get_admin_token()
            except CommandError:
                raise
            except Exception as e:
                raise CommandError(f'Failed to get Keycloak admin token: {e}')
        else:
            admin_token = None

        KEYCLOAK_BASE = os.environ.get('KEYCLOAK_BASE', getattr(settings, 'KEYCLOAK_SERVER_URL', 'http://localhost:8080'))

        processed = 0
        errors = 0

        for iuser in users_qs.iterator():
            try:
                # Resolve role names from DB mapping
                role_names = list(
                    Role.objects.filter(id__in=UserRole.objects.filter(user=iuser, validity_to__isnull=True).values_list('role_id', flat=True)).values_list('name', flat=True)
                )

                self.stdout.write(f'User {iuser.login_name}: roles -> {role_names}')

                # Update local cache used at runtime
                try:
                    cache.set(f'kc_roles_{iuser.id}', role_names, timeout=300)
                    cache.delete('rights_' + str(iuser.id))
                except Exception:
                    pass

                if dry_run:
                    processed += 1
                    continue

                # Perform Keycloak update
                try:
                    user_id = get_kc_user_id(admin_token, KEYCLOAK_BASE, realm, iuser.login_name)
                    if not user_id:
                        self.stderr.write(f'Keycloak user not found for {iuser.login_name} - skipping')
                        errors += 1
                        continue
                    set_kc_openimis_roles(admin_token, KEYCLOAK_BASE, realm, user_id, role_names)
                    self.stdout.write(self.style.SUCCESS(f'Updated Keycloak openimis_roles for {iuser.login_name}'))
                    processed += 1
                    # small delay to avoid hammering Keycloak
                    time.sleep(0.05)
                except Exception as e:
                    self.stderr.write(f'Error updating Keycloak for {iuser.login_name}: {e}')
                    errors += 1
                    continue

            except Exception as e:
                self.stderr.write(f'Internal error for {getattr(iuser, "login_name", iuser)}: {e}')
                errors += 1

        self.stdout.write(f'Done. Processed: {processed}, Errors: {errors}')
