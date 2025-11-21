import os
import time
import secrets
import string
import requests
from core.models.user import User
from core.services.userServices import migration_keycloak_send_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.conf import settings
from core.keycloak_sync import get_admin_token


def fetch_kc_usernames(token, target_realm):
    KEYCLOAK_BASE = os.environ.get("KEYCLOAK_BASE", "http://localhost:8080")
    PAGE = 100
    headers = {"Authorization": f"Bearer {token}"}
    names = set()
    first = 0
    while True:
        params = {"first": first, "max": PAGE}
        url = f"{KEYCLOAK_BASE}/admin/realms/{target_realm}/users"
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        for u in page:
            un = u.get("username")
            if un:
                names.add(un.strip().lower())
        first += len(page)
    return names


def fetch_openimis_users():
    q = 'SELECT "LoginName","EmailId","Phone","LastName","OtherNames" FROM "tblUsers" WHERE "LoginName" IS NOT NULL;'
    with connection.cursor() as cur:
        cur.execute(q)
        rows = cur.fetchall()
    users = []
    for login, email, phone, last, other in rows:
        users.append((
            str(login).strip().lower(),
            (str(email).strip() if email else ""),
            (str(phone).strip() if phone else ""),
            (str(last).strip() if last else ""),
            (str(other).strip() if other else "")
        ))
    return users


def generate_password(length=14):
    alphabet_lower = string.ascii_lowercase
    alphabet_upper = string.ascii_uppercase
    digits = string.digits
    punctuation = "!@#$%^&*()-_=+[]{};:,.<>?"
    pwd = [
        secrets.choice(alphabet_lower),
        secrets.choice(alphabet_upper),
        secrets.choice(digits),
        secrets.choice(punctuation)
    ]
    all_chars = alphabet_lower + alphabet_upper + digits + punctuation
    for _ in range(length - len(pwd)):
        pwd.append(secrets.choice(all_chars))
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


def get_user_id_by_username(token, target_realm, username):
    KEYCLOAK_BASE = os.environ.get("KEYCLOAK_BASE", "http://localhost:8080")
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{KEYCLOAK_BASE}/admin/realms/{target_realm}/users"
    params = {"username": username}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    arr = r.json()
    if not arr:
        return None
    return arr[0].get("id")


def create_kc_user(token, target_realm, loginname, email, phone, last, other, password):
    KEYCLOAK_BASE = os.environ.get("KEYCLOAK_BASE", "http://localhost:8080")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "username": loginname,
        "email": email or None,
        "enabled": True,
        "firstName": other or "",
        "lastName": last or ""
    }
    url = f"{KEYCLOAK_BASE}/admin/realms/{target_realm}/users"
    r = requests.post(url, headers=headers, json=payload)
    if r.status_code == 201:
        loc = r.headers.get("Location", "")
        user_id = loc.rstrip("/").split("/")[-1] if loc else None
    elif r.status_code == 409:
        user_id = get_user_id_by_username(token, target_realm, loginname)
    else:
        raise CommandError(f"User create failed ({r.status_code}): {r.text}")
    if not user_id:
        user_id = get_user_id_by_username(token, target_realm, loginname)
        if not user_id:
            raise CommandError("Cannot determine created user id")
    pw_url = f"{KEYCLOAK_BASE}/admin/realms/{target_realm}/users/{user_id}/reset-password"
    pw_payload = {"type": "password", "value": password, "temporary": True}
    r2 = requests.put(pw_url, headers=headers, json=pw_payload)
    if r2.status_code not in (204, 200):
        raise CommandError(f"Reset password failed ({r2.status_code}): {r2.text}")
    return user_id


class Command(BaseCommand):
    help = 'Create Keycloak users for OpenIMIS users missing in Keycloak'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Do not create users, only list')
        parser.add_argument('--limit', type=int, default=0, help='Limit number of created users (0 = no limit)')
        parser.add_argument('--realm', type=str, default='openimis', help='Target Keycloak realm')
        parser.add_argument('--output', type=str, default='C:\\Users\\gasse\\openimis-be_py\\openIMIS\\created_users.txt', help='Output file for created users')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        target_realm = options['realm']
        output_file = options['output']
        SLEEP_BETWEEN = 0.2

        try:
            token = get_admin_token()
        except Exception as e:
            raise CommandError(f"Cannot get Keycloak admin token: {e}")

        om_users = fetch_openimis_users()
        kc_usernames = fetch_kc_usernames(token, target_realm)

        to_create = [(login, email, phone, last, other) for (login, email, phone, last, other) in om_users if login not in kc_usernames]
        
        self.stdout.write(f'Found {len(to_create)} OpenIMIS users missing in Keycloak')
        
        if dry_run:
            for login, email, phone, last, other in to_create[:limit or None]:
                self.stdout.write(f'SKIP (dry) {login} (email={email} phone={phone})')
            return

        created = 0
        created_users = []
        
        for login, email, phone, last, other in to_create:
            if limit and created >= limit:
                break
            if not (email or phone):
                self.stdout.write(f'SKIP {login}: no email and no phone')
                continue
            try:
                pwd = generate_password()
                uid = create_kc_user(token, target_realm, login, email, phone, last, other, pwd)
                    # Send temporary password by email via migration function
                    # Assume User model exists and is linked to login
                try:
                    user_obj = User.objects.filter(username=login).first()
                    if user_obj:
                        migration_keycloak_send_password(user_obj)
                except Exception as e:
                    self.stderr.write(f'Error sending migration email for {login}: {e}')
                self.stdout.write(f'{login} -> {pwd}')
                created_users.append(f'{login} -> {pwd}')
                created += 1
                time.sleep(SLEEP_BETWEEN)
            except Exception as e:
                self.stderr.write(f'ERROR creating {login}: {e}')
        
        # Write created users to file
        if created_users:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    for user_line in created_users:
                        f.write(user_line + '\n')
                self.stdout.write(f'Created users saved to: {output_file}')
            except Exception as e:
                self.stderr.write(f'Error writing to file {output_file}: {e}')
        else:
            self.stdout.write('No users were created.')
        
        self.stdout.write(f'Total created: {created}')
