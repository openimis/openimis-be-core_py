import json
import uuid

from django.utils.translation import gettext as _

from core.models import User
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import resolve_perm_right_ids
from core.user_types import UT_CLAIM_ADMIN, UT_INTERACTIVE, UT_OFFICER


class RightsRoleGraphQLTestCase(openIMISGraphQLTestCase):
    """Shared assertions for isolated-right and composed-role GraphQL tests."""

    DISTRICT_CODES = ["R1D1", "R2D1", "R2D2"]

    def bearer(self, user):
        token = BaseTestContext(user=user).get_jwt()
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}, token

    def assert_user_has_named_perms(self, user, perm_names):
        rights = resolve_perm_right_ids(perm_names)
        self.assertTrue(
            user.has_perms(rights),
            f"{user.username} missing rights for {perm_names} ({rights})",
        )

    def assert_user_lacks_named_perms(self, user, perm_names):
        rights = resolve_perm_right_ids(perm_names)
        self.assertFalse(
            user.has_perms(rights),
            f"{user.username} unexpectedly has rights for {perm_names}",
        )

    def assert_gql_ok(self, user, query, variables=None):
        headers, _token = self.bearer(user)
        response = self.query(query, headers=headers, variables=variables)
        self.assertResponseNoErrors(response)
        return response

    def assert_gql_unauthorized(self, user, query, variables=None):
        headers, _token = self.bearer(user)
        response = self.query(query, headers=headers, variables=variables)
        content = json.loads(response.content)
        errors = content.get("errors") or []
        unauthorized = _("unauthorized")
        self.assertTrue(
            any(
                marker in (e.get("message") or "").lower()
                for e in errors
                for marker in (unauthorized.lower(), "unauthorized")
            ),
            msg=f"Expected unauthorized for {user.username}, got: {content}",
        )
        return response

    def assert_mutation_ok(self, user, mutation, mutation_uuid):
        headers, token = self.bearer(user)
        response = self.query(mutation, headers=headers)
        self.assertResponseNoErrors(response)
        self.get_mutation_result(mutation_uuid, token)
        return response

    def assert_mutation_permitted(self, user, mutation, mutation_uuid):
        """Permission gate passed; business validation may still fail."""
        headers, token = self.bearer(user)
        response = self.query(mutation, headers=headers)
        self.assertResponseNoErrors(response)
        log = self.get_mutation_result(mutation_uuid, token, allow_exceptions=False)
        payload = json.dumps(log).lower()
        denied_markers = (
            "unauthorized",
            "permissiondenied",
            "not authorized",
            "no_restore_rights",
        )
        self.assertFalse(
            any(marker in payload for marker in denied_markers),
            msg=f"Mutation was denied for {user.username}: {payload}",
        )
        return response

    def assert_mutation_unauthorized(self, user, mutation, mutation_uuid):
        headers, token = self.bearer(user)
        response = self.query(mutation, headers=headers)
        content = json.loads(response.content)
        gql_errors = content.get("errors") or []
        unauthorized = _("unauthorized")
        if any(unauthorized.lower() in (e.get("message") or "").lower() for e in gql_errors):
            return response
        log = self.get_mutation_result(mutation_uuid, token, allow_exceptions=False)
        payload = json.dumps(log).lower()
        markers = (
            "unauthorized",
            "permissiondenied",
            "not authorized",
            "no_restore_rights",
            "no restore",
        )
        self.assertTrue(
            any(marker in payload for marker in markers),
            msg=f"Expected unauthorized mutation for {user.username}, got: {payload}",
        )
        return response

    def create_gql_user_with_hf(
        self,
        admin_user,
        username,
        health_facility,
        roles,
        districts,
        villages=None,
        password="P@ssw0rdGqlHf1!",
        include_officer=True,
        include_claim_admin=True,
    ):
        """
        Create a user the way the CSU form does: GQL createUser with an HF.

        That path attaches ClaimAdmin (HF district filter) and optionally Officer
        (village filter). LocationManager then prefers the CA/HF district over
        villages and UserDistricts.
        """
        user_types = [UT_INTERACTIVE]
        if include_claim_admin:
            user_types.append(UT_CLAIM_ADMIN)
        if include_officer:
            user_types.append(UT_OFFICER)
        cmid = str(uuid.uuid4())
        payload = {
            "username": username,
            "userTypes": user_types,
            "lastName": "GqlHf",
            "otherNames": username,
            "email": f"{username.lower()}@test.openimis.org",
            "language": "en",
            "password": password,
            "roles": [role.id if hasattr(role, "id") else role for role in roles],
            "districts": [d.id if hasattr(d, "id") else d for d in districts],
            "clientMutationId": cmid,
            "clientMutationLabel": f"Create GQL HF user {username}",
        }
        if health_facility is not None:
            payload["healthFacilityId"] = health_facility.id
        if villages:
            payload["villageIds"] = [v.id if hasattr(v, "id") else v for v in villages]
            district_for_eo = villages[0].parent.parent if hasattr(villages[0], "parent") else None
            if district_for_eo is not None:
                payload["locationId"] = district_for_eo.id
        headers, token = self.bearer(admin_user)
        response = self.query(
            """
            mutation ($input: CreateUserMutationInput!) {
              createUser(input: $input) {
                clientMutationId
                internalId
              }
            }
            """,
            headers=headers,
            variables={"input": payload},
        )
        self.assertResponseNoErrors(response)
        self.get_mutation_result(cmid, token)
        user = User.objects.filter(username=username).first()
        self.assertIsNotNone(user, f"GQL createUser did not persist {username}")
        return user
