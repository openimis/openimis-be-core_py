import requests
import os
import django
import sys

# Initialisation Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'openIMIS.settings')
django.setup()

from core.models import InteractiveUser, Role

# Keycloak config (reprend sync_keycloak_roles.py)
KEYCLOAK_BASE = "http://localhost:8080"
REALM = "openimis"
ADMIN_REALM = "master"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
CLIENT_ID = "admin-cli"

def get_admin_token():
    url = f"{KEYCLOAK_BASE}/realms/{ADMIN_REALM}/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "username": ADMIN_USER,
        "password": ADMIN_PASS
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

def get_user_id(token, username):
    url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"username": username}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    users = r.json()
    for u in users:
        if u.get("username", "").lower() == username.lower():
            return u["id"]
    return None

def get_openimis_roles_keycloak(token, user_id):
    url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users/{user_id}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    user_data = r.json()
    attrs = user_data.get("attributes", {})
    return attrs.get("openimis_roles", None)

if len(sys.argv) > 2 and sys.argv[1] == '--user':
    login_filter = sys.argv[2]
    users = InteractiveUser.objects.filter(login_name=login_filter, validity_to__isnull=True)
else:
    users = InteractiveUser.objects.filter(validity_to__isnull=True)

token = get_admin_token()
for iuser in users:
    username = iuser.login_name
    # Roles côté OpenIMIS
    # Try Keycloak openimis_roles first
    kc_roles = None
    if hasattr(iuser, '_get_keycloak_roles'):
        kc_roles = iuser._get_keycloak_roles()
    if kc_roles is not None:
        roles = Role.objects.filter(name__in=kc_roles)
        print(f"User: {username}")
        for r in roles:
            print(f"  KC Role: {r.name} (roleID: {r.id})")
    else:
        # Fallback to DB
        from core.models import UserRole
        roles = Role.objects.filter(
            id__in=UserRole.objects.filter(user=iuser).values_list('role_id', flat=True)
        )
        print(f"User: {username}")
        for r in roles:
            print(f"  DB Role: {r.name} (roleID: {r.id})")
    # Rôles côté Keycloak
    user_id = get_user_id(token, username)
    if user_id:
        kc_roles = get_openimis_roles_keycloak(token, user_id)
        print(f"  Keycloak openimis_roles: {kc_roles}")
    else:
        print("  [WARN] Utilisateur Keycloak non trouvé")
