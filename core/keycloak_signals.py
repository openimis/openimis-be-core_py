"""
Signal handlers for automatic synchronization of Keycloak/OpenIMIS roles at login.
LOGIC STRICTLY IDENTICAL TO THE SCRIPT set_openimis-roles_from_keycloak-attributes.py
"""
import logging
import requests
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.conf import settings
from django.apps import apps
from django.apps import apps as django_apps
from core.models import InteractiveUser, UserRole, Role
from core.utils import filter_validity

logger = logging.getLogger(__name__)


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


def get_openimis_locations_keycloak(token, user_id):
    """
    Retrieve openimis_location attributes from Keycloak user admin endpoint.
    Returns a list (possibly empty) of location codes (strings).
    """
    url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users/{user_id}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    user_data = r.json()
    attrs = user_data.get("attributes", {})
    # Keycloak may expose a single value or a list under the same key
    locs = attrs.get("openimis_location", [])
    return locs


def _debug_process_openimis_locations(kc_locations):
    """
    Given a list of Keycloak location codes, resolve them in the DB and
    print helpful debug information:
      - if region: list related districts
      - if district: just print the district
      - if ward: list related villages
    This is intentionally read-only and only prints to console.
    """
    if not kc_locations:
        print("  Keycloak openimis_location: []")
        return

    try:
        Location = apps.get_model("location", "Location")
    except Exception as e:
        print(f"  [WARN] Location model not available: {e}")
        return

    for code in kc_locations:
        print(f"  Keycloak openimis_location: {code}")
        try:
            # Try common fields where a code might be stored
            loc = None
            # Try 'code' field first
            try:
                loc = Location.objects.filter(code=code).first()
            except Exception:
                loc = None

            # Fallback: try uuid/identifier
            if not loc:
                try:
                    loc = Location.objects.filter(uuid=code).first()
                except Exception:
                    loc = None

            if not loc:
                print(f"    [NOT FOUND IN DB] {code}")
                continue

            # Determine location type from known fields
            loc_type = getattr(loc, 'location_type', None) or getattr(loc, 'type', None) or getattr(loc, 'loc_type', None)
            loc_name = getattr(loc, 'name', str(loc))
            loc_code = getattr(loc, 'code', getattr(loc, 'uuid', None))
            print(f"    Found: {loc_code} - {loc_name} (type: {loc_type})")

            # Normalize type check by uppercasing string value when present
            t = str(loc_type).upper() if loc_type is not None else ''

            if t.startswith('R') or t == 'REGION':
                # Region -> list districts (children of this location with type D)
                districts = Location.objects.filter(parent=loc)
                print(f"    Region -> districts ({districts.count()}):")
                for d in districts:
                    d_code = getattr(d, 'code', getattr(d, 'uuid', d.id))
                    print(f"      - {d_code} : {getattr(d,'name', d_code)}")
            elif t.startswith('W') or t == 'WARD':
                # Ward -> list villages
                villages = Location.objects.filter(parent=loc)
                print(f"    Ward -> villages ({villages.count()}):")
                for v in villages:
                    v_code = getattr(v, 'code', getattr(v, 'uuid', v.id))
                    print(f"      - {v_code} : {getattr(v,'name', v_code)}")
            else:
                # District or others: just display
                print(f"    (No additional expansion for type '{loc_type}')")

        except Exception as e:
            print(f"    [ERROR] while processing {code}: {e}")


@receiver(user_logged_in)
def sync_keycloak_roles_on_login(sender, request, user, **kwargs):
    """
    Signal executed automatically after each successful login.
    Synchronizes Keycloak roles (openimis_roles attribute) to OpenIMIS (tblUserRole).
    """
    try:
        # Retrieve the corresponding InteractiveUser
        if hasattr(user, 'i_user') and user.i_user:
            iuser = user.i_user
        elif hasattr(user, 'username'):
            try:
                iuser = InteractiveUser.objects.get(login_name=user.username, validity_to__isnull=True)
            except InteractiveUser.DoesNotExist:
                logger.warning(f"[KeycloakSync] No InteractiveUser found for {user.username}")
                return
        else:
            logger.warning(f"[KeycloakSync] User without username: {user}")
            return

        username = iuser.login_name
        logger.info(f"[KeycloakSync] Starting synchronization for {username}")
        print(f"\n==============================")
        print(f"[KeycloakSync] LOGIN: {username}")
        print(f"==============================")


        # LOGIC EXACTLY IDENTICAL TO THE SCRIPT
        token = get_admin_token()
        user_id = get_user_id(token, username)
        if user_id:
            kc_roles = get_openimis_roles_keycloak(token, user_id) or []
            kc_roles_set = set(kc_roles)
            print(f"  Keycloak openimis_roles: {kc_roles}")
            # Add missing roles
            for role_name in kc_roles:
                try:
                    role_obj = Role.objects.get(name=role_name)
                    has_userrole = UserRole.objects.filter(user=iuser, role=role_obj).exists()
                    if not has_userrole:
                        UserRole.objects.create(user=iuser, role=role_obj)
                        print(f"    {role_name} (roleID: {role_obj.id}) - tblUserRole: False -> ADDED")
                    else:
                        print(f"    {role_name} (roleID: {role_obj.id}) - tblUserRole: True")
                except Role.DoesNotExist:
                    print(f"    {role_name} (roleID: NOT FOUND) - tblUserRole: False")
            # Remove roles present in DB but not in Keycloak
            db_roles = UserRole.objects.filter(user=iuser)
            for userrole in db_roles:
                if userrole.role.name not in kc_roles_set:
                    print(f"    {userrole.role.name} (roleID: {userrole.role.id}) - tblUserRole: True -> REMOVED")
                    userrole.delete()
            # Invalidate user rights cache
            try:
                from django.core.cache import cache
                cache.delete(f"rights_{iuser.id}")
            except Exception as e:
                logger.warning(f"[KeycloakSync] Error invalidating rights cache: {e}")
            # --- Synchronize districts from openimis_location attribute ---
            try:
                # Retrieve all Keycloak info in a single request
                url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users/{user_id}"
                headers = {"Authorization": f"Bearer {token}"}
                r = requests.get(url, headers=headers)
                r.raise_for_status()
                user_data = r.json()
                attrs = user_data.get("attributes", {})
                kc_locations = attrs.get("openimis_location", []) or []
                print(f"  Keycloak openimis_location (raw): {kc_locations}")
                try:
                    Location = apps.get_model("location", "Location")
                except Exception as e:
                    print(f"    [WARN] Location model not available: {e}")
                    Location = None

                district_ids = set()
                village_ids = set()
                if Location:
                    if '*' in kc_locations:
                        all_districts = Location.objects.filter(type__iexact='D')
                        district_ids.update([d.id for d in all_districts])
                        print(f"    [SYNC] '*' detected, all districts added: {[d.id for d in all_districts]}")
                    else:
                        # Use a single filter for all codes and UUIDs
                        locs = list(Location.objects.filter(code__in=kc_locations) | Location.objects.filter(uuid__in=kc_locations))
                        found_codes = set()
                        for loc in locs:
                            found_codes.add(getattr(loc, 'code', None))
                            loc_type = getattr(loc, 'location_type', None) or getattr(loc, 'type', None) or getattr(loc, 'loc_type', None)
                            t = str(loc_type).upper() if loc_type is not None else ''
                            
                            if t.startswith('R') or t == 'REGION':
                                # Region -> get all districts (children)
                                child_districts = Location.objects.filter(parent=loc)
                                district_ids.update([d.id for d in child_districts])
                                print(f"    [SYNC] Region {loc.code} -> districts added: {[d.id for d in child_districts]}")
                                
                            elif t.startswith('D') or t == 'DISTRICT':
                                # District -> add district
                                district_ids.add(loc.id)
                                print(f"    [SYNC] District added: {loc.id}")
                                
                            elif t.startswith('W') or t == 'WARD' or t.startswith('M') or t == 'MUNICIPALITY':
                                # Ward/Municipality -> get all villages (children)
                                child_villages = Location.objects.filter(parent=loc)
                                for village in child_villages:
                                    village_ids.add(village.id)
                                    print(f"    [SYNC] Village added from {t} {loc.code}: {village.id}")
                                    
                                    # Add district parent of the village if missing
                                    village_parent = village.parent  # This is the ward/municipality
                                    if village_parent and village_parent.parent:  # District is grandparent of village
                                        district_parent = village_parent.parent
                                        if district_parent.id not in district_ids:
                                            district_ids.add(district_parent.id)
                                            print(f"    [SYNC] District parent added via village: {district_parent.id}")
                            else:
                                # Unknown type - check if has village children
                                potential_villages = Location.objects.filter(parent=loc)
                                for child in potential_villages:
                                    child_type = getattr(child, 'location_type', None) or getattr(child, 'type', None) or getattr(child, 'loc_type', None)
                                    child_t = str(child_type).upper() if child_type is not None else ''
                                    if child_t.startswith('V') or child_t == 'VILLAGE' or not child_t:
                                        village_ids.add(child.id)
                                        print(f"    [SYNC] Village added from unknown parent type: {child.id}")
                                        # Add district parent
                                        if loc.parent:
                                            district_parent = loc.parent
                                            if district_parent.id not in district_ids:
                                                district_ids.add(district_parent.id)
                                                print(f"    [SYNC] District parent added via village: {district_parent.id}")
                        
                        # Show codes not found
                        for code in kc_locations:
                            if code not in found_codes and code != '*':
                                print(f"    [SYNC] location code not found in DB: {code}")

                # Sync districts (existing logic - don't touch)
                UserDistrict = django_apps.get_model("location", "UserDistrict")
                db_districts = set(UserDistrict.objects.filter(user=iuser, validity_to__isnull=True).values_list('location_id', flat=True))
                for did in district_ids:
                    if did not in db_districts:
                        UserDistrict.objects.create(user=iuser, location_id=did, audit_user_id=getattr(iuser, 'audit_user_id', 2))
                        print(f"    [SYNC] District added to UserDistrict: {did}")
                for did in db_districts:
                    if did not in district_ids:
                        UserDistrict.objects.filter(user=iuser, location_id=did, validity_to__isnull=True).delete()
                        print(f"    [SYNC] District removed from UserDistrict: {did}")

                # Sync villages to tblOfficerVillages
                if village_ids:
                    try:
                        OfficerVillage = django_apps.get_model("location", "officervillage")
                        Officer = django_apps.get_model("core", "Officer")
                        
                        # Get Officer object from InteractiveUser
                        try:
                            officer = Officer.objects.get(code=iuser.login_name, validity_to__isnull=True)
                            print(f"    [SYNC] Officer found: {officer.id}")
                        except Officer.DoesNotExist:
                            print(f"    [WARN] No Officer found for user {iuser.login_name}")
                            officer = None
                        
                        if officer:
                            db_villages = set(OfficerVillage.objects.filter(officer=officer, validity_to__isnull=True).values_list('location_id', flat=True))
                            
                            # Add missing villages
                            for vid in village_ids:
                                if vid not in db_villages:
                                    OfficerVillage.objects.create(officer=officer, location_id=vid, audit_user_id=getattr(iuser, 'audit_user_id', 2))
                                    print(f"    [SYNC] Village added to tblOfficerVillages: {vid}")
                            
                            # Remove villages no longer needed
                            for vid in db_villages:
                                if vid not in village_ids:
                                    OfficerVillage.objects.filter(officer=officer, location_id=vid, validity_to__isnull=True).delete()
                                    print(f"    [SYNC] Village removed from tblOfficerVillages: {vid}")
                                    
                    except Exception as e:
                        print(f"    [WARN] Failed to sync tblOfficerVillages: {e}")
                else:
                    print(f"    [SYNC] No villages to sync")
            except Exception as e:
                print(f"  [WARN] Failed to process/sync openimis_location attributes: {e}")
        else:
            print("  [WARN] Keycloak user not found")

        print(f"==============================\n")
        logger.info(f"[KeycloakSync] Synchronization finished for {username}")

    except Exception as e:
        logger.error(f"[KeycloakSync] Error during synchronization: {e}", exc_info=True)
        print(f"[KeycloakSync][ERROR] {e}")
