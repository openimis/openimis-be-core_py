import os
import time
import requests
from flask import Flask, request, jsonify

KEYCLOAK_BASE = os.environ.get('KEYCLOAK_BASE', 'http://keycloak:8080')
REALM = os.environ.get('KEYCLOAK_REALM', 'master')
ADMIN_USER = os.environ.get('KEYCLOAK_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('KEYCLOAK_ADMIN_PASSWORD', 'admin')

app = Flask(__name__)



def get_admin_token():
    url = f"{KEYCLOAK_BASE}/realms/master/protocol/openid-connect/token"
    data = {
        'grant_type': 'password',
        'client_id': 'admin-cli',
        'username': ADMIN_USER,
        'password': ADMIN_PASS
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json().get('access_token')


def find_keycloak_user_id(token, username):
    url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users"
    headers = {'Authorization': f'Bearer {token}'}
    params = {'username': username}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    users = r.json()
    for u in users:
        if u.get('username', '').lower() == username.lower():
            return u.get('id')
    return None


def get_realm_role(token, role_name):
    """Return role representation for a realm role name, or None if not found."""
    url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/roles/{role_name}"
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json()
    return None


def get_keycloak_profile(token, username):
    user_id = find_keycloak_user_id(token, username)
    if not user_id:
        return None
    url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users/{user_id}"
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    data = r.json()
    profile = {
        'username': data.get('username'),
        'firstName': data.get('firstName'),
        'lastName': data.get('lastName'),
        'email': data.get('email')
    }
    # collect openimis_roles attribute if present
    attrs = data.get('attributes', {})
    kc_roles = attrs.get('openimis_roles') if attrs else None
    if kc_roles:
        # normalize
        if isinstance(kc_roles, list):
            roles_flat = []
            for r in kc_roles:
                if isinstance(r, str):
                    roles_flat.extend([x.strip() for x in r.split(',') if x.strip()])
            kc_roles = roles_flat
        elif isinstance(kc_roles, str):
            kc_roles = [r.strip() for r in kc_roles.split(',') if r.strip()]
        profile['roles'] = kc_roles
    return profile

@app.route('/profile')
def profile():
    username = request.args.get('username')
    if not username:
        return jsonify({'error': 'username required, e.g. /profile?username=alice'}), 400

    try:
        token = get_admin_token()
        kc = get_keycloak_profile(token, username)
        if not kc:
            return jsonify({'error': 'user not found in Keycloak'}), 404
        return jsonify({'keycloak': kc, 'effective': kc})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    


@app.route('/create-test-user', methods=['POST'])
def create_test_user():
    """Create a Keycloak user and optionally set openimis_roles attribute.
    JSON body: {"username":"alice","firstName":"Alice","lastName":"X","email":"a@b.com","roles":["r1"]}
    """
    data = request.get_json() or {}
    username = data.get('username')
    if not username:
        return jsonify({'error': 'username required in JSON body'}), 400
    first = data.get('firstName')
    last = data.get('lastName')
    email = data.get('email')
    roles = data.get('roles')
    password = data.get('password')

    try:
        token = get_admin_token()
        # create user
        url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        user_payload = {'username': username, 'enabled': True}
        if first: user_payload['firstName'] = first
        if last: user_payload['lastName'] = last
        if email: user_payload['email'] = email
        if password:
            user_payload['credentials'] = [{
                'type': 'password',
                'value': password,
                'temporary': False
            }]
        if password:
            user_payload['credentials'] = [{
                'type': 'password',
                'value': password,
                'temporary': False
            }]
        r = requests.post(url, headers=headers, json=user_payload)
        # 201 on success; if user exists Keycloak returns 409
        if r.status_code not in (201, 409):
            return jsonify({'error': 'failed to create user', 'status': r.status_code, 'body': r.text}), 500
        # find user id
        user_id = find_keycloak_user_id(token, username)
        if not user_id:
            return jsonify({'error': 'created but cannot find id'}), 500
        # Always update firstName, lastName, email, and attributes (roles) after creation or if user exists
        user_url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users/{user_id}"
        update_payload = {}
        if first:
            update_payload['firstName'] = first
        if last:
            update_payload['lastName'] = last
        if email:
            update_payload['email'] = email
        if roles:
            # Keycloak expects attributes as dict of lists
            update_payload['attributes'] = {'openimis_roles': roles}
        if update_payload:
            r2 = requests.put(user_url, headers=headers, json=update_payload)
            if r2.status_code not in (204, 200):
                return jsonify({'error': 'failed to update user fields', 'status': r2.status_code, 'body': r2.text}), 500
        # Assign realm roles if provided
        assign_role_names = []
        if roles and isinstance(roles, list):
            assign_role_names.extend([r for r in roles if isinstance(r, str)])
        if assign_role_names:
            role_mappings_url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/users/{user_id}/role-mappings/realm"
            mapping_list = []
            for rn in assign_role_names:
                # fetch role representation
                role_repr = get_realm_role(token, rn)
                if not role_repr:
                    # try to create the realm role if it doesn't exist
                    create_role_url = f"{KEYCLOAK_BASE}/admin/realms/{REALM}/roles"
                    try:
                        rc = requests.post(create_role_url, headers=headers, json={'name': rn})
                        if rc.status_code in (201, 409):
                            role_repr = get_realm_role(token, rn)
                    except Exception:
                        role_repr = None
                if role_repr:
                    # include id and name as Keycloak expects
                    mapping_list.append({'id': role_repr.get('id'), 'name': role_repr.get('name')})
            if mapping_list:
                r3 = requests.post(role_mappings_url, headers=headers, json=mapping_list)
                # Keycloak returns 204 on success
                if r3.status_code not in (204, 201, 200):
                    return jsonify({'error': 'failed to assign roles', 'status': r3.status_code, 'body': r3.text}), 500
        return jsonify({'status': 'ok', 'user_id': user_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # allow Keycloak to boot in dev runs
    print('Starting mosip-mock...')
    app.run(host='0.0.0.0', port=5000)
