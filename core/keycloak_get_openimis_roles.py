import django
import sys
import os
import requests
from core.models import Role
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'openIMIS.settings')
django.setup()

"""
Authentication on the master realm, retrieval of users on the target realm
KEYCLOAK_REALM = authentication realm (master)
KEYCLOAK_TARGET_REALM = realm from which to list users (e.g., openimis)
"""
KEYCLOAK_URL = os.environ.get('KEYCLOAK_URL', 'http://localhost:8080')
KEYCLOAK_REALM = os.environ.get('KEYCLOAK_REALM', 'master')
KEYCLOAK_TARGET_REALM = os.environ.get('KEYCLOAK_TARGET_REALM', 'openimis')
KEYCLOAK_ADMIN_USER = os.environ.get('KEYCLOAK_ADMIN_USER', 'admin')
KEYCLOAK_ADMIN_PASSWORD = os.environ.get('KEYCLOAK_ADMIN_PASSWORD', 'admin')
KEYCLOAK_CLIENT_ID = os.environ.get('KEYCLOAK_CLIENT_ID', 'admin-cli')


def get_admin_token():
    url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
    data = {
        'grant_type': 'password',
        'client_id': KEYCLOAK_CLIENT_ID,
        'username': KEYCLOAK_ADMIN_USER,
        'password': KEYCLOAK_ADMIN_PASSWORD,
    }
    resp = requests.post(url, data=data)
    resp.raise_for_status()
    return resp.json()['access_token']


def get_users(token, username=None):
    headers = {'Authorization': f'Bearer {token}'}
    # Target the desired realm for user retrieval
    if username:
        url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_TARGET_REALM}/users"
        params = {'username': username}
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
    else:
        url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_TARGET_REALM}/users"
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


def get_openimis_roles(user):
    attrs = user.get('attributes', {})
    roles = attrs.get('openimis_roles', None)
    return roles


def main():
    username = None
    if len(sys.argv) > 2 and sys.argv[1] == '--user':
        username = sys.argv[2]
    token = get_admin_token()
    users = get_users(token, username)
    if not users:
        print('No user found.')
        return
    for user in users:
        uname = user.get('username')
        roles = get_openimis_roles(user)
        print(f"User: {uname}\n  openimis_roles: {roles}")
        if roles:
            for role_name in roles:
                try:
                    role_obj = Role.objects.get(name=role_name)
                    print(f"    Role: {role_name} => id: {role_obj.id}")
                except Role.DoesNotExist:
                    print(f"    Role: {role_name} => NOT FOUND in tblRole")

if __name__ == '__main__':
    main()
