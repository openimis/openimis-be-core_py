"""
Helper utilities for Keycloak <-> OpenIMIS sync operations.

Provides functions used by management commands and signal handlers:
- get_admin_token
- get_kc_user_id
- get_openimis_roles_keycloak
- set_kc_openimis_roles
"""

import os
import requests
from django.conf import settings


KEYCLOAK_BASE = os.environ.get("KEYCLOAK_BASE", getattr(settings, 'KEYCLOAK_SERVER_URL', 'http://localhost:8080'))
REALM = os.environ.get('KEYCLOAK_REALM', getattr(settings, 'KEYCLOAK_REALM', 'openimis'))
ADMIN_REALM = os.environ.get('KEYCLOAK_ADMIN_REALM', 'master')
ADMIN_USER = os.environ.get('KEYCLOAK_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('KEYCLOAK_ADMIN_PASS', 'admin')
CLIENT_ID = os.environ.get('KEYCLOAK_ADMIN_CLIENT_ID', 'admin-cli')


def get_admin_token():
	"""Obtain an admin access token from Keycloak using password grant."""
	url = f"{KEYCLOAK_BASE}/realms/{ADMIN_REALM}/protocol/openid-connect/token"
	data = {
		"grant_type": "password",
		"client_id": CLIENT_ID,
		"username": ADMIN_USER,
		"password": ADMIN_PASS,
	}
	r = requests.post(url, data=data, timeout=10)
	r.raise_for_status()
	return r.json()["access_token"]


def get_kc_user_id(token, base, realm, username):
	"""Return Keycloak user id for a username (case-insensitive prefer exact match)."""
	headers = {"Authorization": f"Bearer {token}"}
	url = f"{base}/admin/realms/{realm}/users"
	params = {"username": username}
	r = requests.get(url, headers=headers, params=params, timeout=10)
	r.raise_for_status()
	arr = r.json()
	if not arr:
		return None
	for u in arr:
		if u.get('username', '').lower() == username.lower():
			return u.get('id')
	return arr[0].get('id')


def get_openimis_roles_keycloak(token, base, realm, user_id):
	"""Fetch the Keycloak user's attributes and return the 'openimis_roles' attribute (list or None)."""
	headers = {"Authorization": f"Bearer {token}"}
	url = f"{base}/admin/realms/{realm}/users/{user_id}"
	r = requests.get(url, headers=headers, timeout=10)
	r.raise_for_status()
	user_data = r.json()
	attrs = user_data.get('attributes', {})
	return attrs.get('openimis_roles', None)


def set_kc_openimis_roles(token, base, realm, user_id, role_names):
	"""
	Set the Keycloak user's attribute openimis_roles to the supplied list (or empty list).
	
	CRITICAL: Preserves all other user attributes (email, firstName, lastName, etc.)
	by first fetching the user, merging openimis_roles with existing attributes, then updating.
	"""
	headers = {"Authorization": f"Bearer {token}", 'Content-Type': 'application/json'}
	url = f"{base}/admin/realms/{realm}/users/{user_id}"
	
	# Step 1: GET existing user data to preserve all attributes
	r_get = requests.get(url, headers=headers, timeout=10)
	r_get.raise_for_status()
	user_data = r_get.json()
	
	# Step 2: Merge openimis_roles into existing attributes
	existing_attrs = user_data.get('attributes', {})
	existing_attrs['openimis_roles'] = role_names
	
	# Step 3: PUT back with ALL attributes (including email, firstName, lastName from user_data)
	# IMPORTANT: We need to preserve the top-level fields too (email, firstName, lastName)
	# so we only update the attributes field, keeping the rest of user_data intact
	body = {
		'attributes': existing_attrs,
		'email': user_data.get('email'),
		'firstName': user_data.get('firstName'),
		'lastName': user_data.get('lastName')
	}
	r = requests.put(url, headers=headers, json=body, timeout=10)
	r.raise_for_status()
	return True
