"""
Middleware for automatic synchronization of Keycloak/OpenIMIS roles.
Triggered on each authenticated request and synchronizes roles if necessary.
"""
import logging
import requests
import time
import os
import json
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from core.models import InteractiveUser, UserRole, Role

logger = logging.getLogger(__name__)


# Cache to avoid synchronizing the same user too often
_last_sync_cache = {}
SYNC_COOLDOWN = 300  # 5 minutes between each sync for the same user

KEYCLOAK_BASE = getattr(settings, 'KEYCLOAK_SERVER_URL', 'http://localhost:8080')
REALM = getattr(settings, 'KEYCLOAK_REALM', 'openimis')
ADMIN_REALM = "master"
ADMIN_USER = getattr(settings, 'KEYCLOAK_ADMIN_USER', 'admin')
ADMIN_PASS = getattr(settings, 'KEYCLOAK_ADMIN_PASSWORD', 'admin')
CLIENT_ID = "admin-cli"


def get_admin_token():
    """Obtains a Keycloak admin token to access the admin API."""
    url = f"{KEYCLOAK_BASE}/realms/{ADMIN_REALM}/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "username": ADMIN_USER,
        "password": ADMIN_PASS
    }
    try:
        r = requests.post(url, data=data)
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        logger.error(f"[KeycloakSync] Error obtaining admin token: {e}")
        return None


def get_user_id(token, username):
    """Retrieves the Keycloak user ID from the username."""
    url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"username": username}
    try:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        users = r.json()
        for u in users:
            if u.get("username", "").lower() == username.lower():
                return u["id"]
    except Exception as e:
        logger.error(f"[KeycloakSync] Error retrieving user ID: {e}")
    return None


def get_openimis_roles_keycloak(token, user_id):
    """Retrieves openimis_roles attributes from Keycloak."""
    url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users/{user_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        user_data = r.json()
        attrs = user_data.get("attributes", {})
        return attrs.get("openimis_roles", None)
    except Exception as e:
        logger.error(f"[KeycloakSync] Error retrieving roles: {e}")
    return None


def sync_user_roles(username):
    """
    Synchronizes Keycloak roles to OpenIMIS for a given user.
    Uses exactly the same logic as the script print_openimis_roles_full.py
    """
    try:
        # Retrieve the InteractiveUser
        try:
            iuser = InteractiveUser.objects.get(login_name=username, validity_to__isnull=True)
        except InteractiveUser.DoesNotExist:
            logger.warning(f"[KeycloakSync] No InteractiveUser found for {username}")
            return False

        logger.info(f"[KeycloakSync] Starting synchronization for {username}")
        print(f"\n==============================")
        print(f"[KeycloakSync] MIDDLEWARE SYNC: {username}")
        print(f"==============================")

        # Obtient un token admin Keycloak
        token = get_admin_token()
        if not token:
            logger.error("[KeycloakSync] Impossible d'obtenir le token admin")
            print("[KeycloakSync][ERROR] Token admin non disponible")
            return False

        # Affiche les rôles DB actuels
        # Try Keycloak openimis_roles first
        user_id = get_user_id(token, username)
        kc_roles = None
        if user_id:
            kc_roles = get_openimis_roles_keycloak(token, user_id)
        if kc_roles is not None:
            print(f"User: {username}")
            roles = Role.objects.filter(name__in=kc_roles)
            for r in roles:
                print(f"  KC Role: {r.name} (roleID: {r.id})")
            print(f"  Keycloak openimis_roles: {kc_roles}")
        else:
            # Fallback to DB
            from core.models import UserRole
            db_roles = Role.objects.filter(
                id__in=UserRole.objects.filter(user=iuser).values_list('role_id', flat=True)
            )
            print(f"User: {username}")
            for r in db_roles:
                print(f"  DB Role: {r.name} (roleID: {r.id})")
        print(f"==============================\n")
        logger.info(f"[KeycloakSync] Synchronisation terminée pour {username}")
        return True

    except Exception as e:
        logger.error(f"[KeycloakSync] Erreur lors de la synchronisation: {e}", exc_info=True)
        print(f"[KeycloakSync][ERROR] {e}")
        return False


class KeycloakRoleSyncMiddleware(MiddlewareMixin):
    """
    Middleware that detects authenticated users and synchronizes their Keycloak roles.
    Automatically triggered on every authenticated request.
    """

    def process_request(self, request):
        # Synchronize ONLY at each login (POST on /login or GraphQL login mutation)
        is_login = False
        if request.method == 'POST' and request.path in ['/login', '/api/login', '/accounts/login/']:
            is_login = True
        # For GraphQL, detect login mutation
        if request.method == 'POST' and request.path == '/api/graphql':
            try:
                body = request.body.decode('utf-8')
                if 'login' in body:
                    is_login = True
            except Exception:
                pass
        if not is_login:
            return None


        # Check if the user is authenticated
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return None

        # Retrieve the username
        username = None
        if hasattr(request.user, 'i_user') and request.user.i_user:
            username = request.user.i_user.login_name
        elif hasattr(request.user, 'username'):
            username = request.user.username
        else:
            return None

        # Log file + console
        log_path = os.path.join(os.path.dirname(__file__), '..', '..', 'keycloak_sync_debug.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[KeycloakSync] SYNC at login for {username}\n")
        print(f"[KeycloakSync] SYNC at login for {username}")

    # --- LOGIC STRICTLY IDENTICAL TO THE MANUAL SCRIPT ---
        import requests
        KEYCLOAK_BASE = 'http://localhost:8080'
        REALM = 'openimis'
        ADMIN_REALM = 'master'
        ADMIN_USER = 'admin'
        ADMIN_PASS = 'admin'
        CLIENT_ID = 'admin-cli'

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
            # Very visible printout of attributes and openimis_roles key
            print("\n\n===========================")
            print(f"[KeycloakSync][VISIBLE] KEYCLOAK ATTRIBUTES FOR USER: {user_data.get('username', user_id)}")
            print(f"Attributes: {attrs}")
            print(f"openimis_roles: {attrs.get('openimis_roles', None)}")
            print("===========================\n\n")
            return attrs.get("openimis_roles", None)

    # Execute the synchronization
        try:
            token = get_admin_token()
            from core.models import InteractiveUser, UserRole, Role
            try:
                iuser = InteractiveUser.objects.get(login_name=username, validity_to__isnull=True)
            except Exception:
                print(f"[KeycloakSync][ERROR] No InteractiveUser found for {username}")
                return None
            roles = Role.objects.filter(id__in=UserRole.objects.filter(user=iuser).values_list('role_id', flat=True))
            print(f"User: {username}")
            for r in roles:
                print(f"  DB Role: {r.name} (roleID: {r.id})")
            user_id = get_user_id(token, username)
            if user_id:
                # Retrieve the full user_data for display
                url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users/{user_id}"
                headers = {"Authorization": f"Bearer {token}"}
                r = requests.get(url, headers=headers)
                r.raise_for_status()
                user_data = r.json()
                attrs = user_data.get("attributes", {})
                kc_roles = attrs.get("openimis_roles", None)
                # Very visible printout at each login
                print("\n\n===========================")
                print(f"[KeycloakSync][VISIBLE] KEYCLOAK ATTRIBUTES FOR USER: {user_data.get('username', user_id)}")
                print(f"Attributes: {attrs}")
                print(f"openimis_roles: {kc_roles}")
                print("===========================\n\n")
                print(f"  [DEBUG] Raw openimis_roles attribute: {kc_roles} (type: {type(kc_roles)})")
                # --- PARSING STRICTLY IDENTICAL TO THE SCRIPT ---
                if kc_roles:
                    print("  Keycloak openimis_roles:")
                    if isinstance(kc_roles, list):
                        roles_flat = []
                        for r in kc_roles:
                            if isinstance(r, str):
                                roles_flat.extend([x.strip() for x in r.split(',') if x.strip()])
                        kc_roles = roles_flat
                    elif isinstance(kc_roles, str):
                        kc_roles = [r.strip() for r in kc_roles.split(',') if r.strip()]
                    else:
                        kc_roles = []
                    print(f"  [DEBUG] openimis_roles attribute after parsing: {kc_roles}")
                    for role_name in kc_roles:
                        try:
                            role_obj = Role.objects.get(name=role_name)
                            has_userrole = UserRole.objects.filter(user=iuser, role=role_obj).exists()
                            if not has_userrole:
                                UserRole.objects.create(user=iuser, role=role_obj)
                                print(f"    {role_name} (roleID: {role_obj.id}) - tblUserRole: False -> ADDED")
                                logger.info(f"[KeycloakSync] Added role {role_name} (roleID: {role_obj.id}) to user {username}")
                            else:
                                print(f"    {role_name} (roleID: {role_obj.id}) - tblUserRole: True")
                                logger.info(f"[KeycloakSync] Role {role_name} (roleID: {role_obj.id}) already present for user {username}")
                        except Role.DoesNotExist:
                            print(f"    {role_name} (roleID: NOT FOUND) - tblUserRole: False")
                            logger.warning(f"[KeycloakSync] Role {role_name} not found in DB for user {username}")
                else:
                    print("  Keycloak openimis_roles: []")
                    logger.info(f"[KeycloakSync] No Keycloak roles found for user {username}")
            else:
                print("  [WARN] Keycloak user not found")
                logger.warning(f"[KeycloakSync] Keycloak user not found for {username}")
        except Exception as e:
            print(f"[KeycloakSync][ERROR] {e}")
        return None