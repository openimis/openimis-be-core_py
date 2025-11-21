from .jwt import jwt_decode_user_key

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import Throttled
from rest_framework import exceptions
from graphql_jwt.utils import get_credentials
from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.shortcuts import get_user_by_token
from core.apps import CoreConfig
from django.conf import settings
from django_ratelimit.core import is_ratelimited
from core.models import Role

from datetime import date
import jwt
import logging

logger = logging.getLogger(__file__)


class JWTAuthentication(BaseAuthentication):
    """
    class to obtain token from header if it is provided
    and verify if this is correct/valid token
    """

    def authenticate(self, request):
        self.check_rate_limit(request)
        token = get_credentials(request)
        if token:
            # Do not pass context to avoid to try to get user from request to get his private key.
            try:
                user = get_user_by_token(token)
            except (jwt.PyJWTError, JSONWebTokenError) as exc:
                raise exceptions.AuthenticationFailed("INCORRECT_CREDENTIALS") from exc
            except Exception as exc:
                raise exceptions.AuthenticationFailed(str(exc)) from exc
            else:
                if CoreConfig.is_valid_health_facility_contract_required:
                    if not (hasattr(user, 'health_facility') and hasattr(user.health_facility, 'contract_end_date') and
                            user.health_facility.contract_end_date > date.today()):
                        raise exceptions.AuthenticationFailed("HF_CONTRACT_INVALID")

                # Check Keycloak role validation when Keycloak is enabled
                if getattr(settings, 'KEYCLOAK_ENABLED', False):
                    self.validate_keycloak_roles(user)

            return user, None

    def enforce_csrf(self, request):
        return  # To not perform the csrf during checking auth header

    @staticmethod
    def check_rate_limit(request) -> None:
        group = settings.RATELIMIT_GROUP
        key = settings.RATELIMIT_KEY
        rate = settings.RATELIMIT_RATE
        mode = settings.MODE

        if mode == 'PROD' and is_ratelimited(
                request=request,
                group=group,
                fn=None,
                key=key,
                rate=rate,
                method=is_ratelimited.ALL,
                increment=True
        ):
            raise Throttled(detail='Rate limit exceeded')

    def validate_keycloak_roles(self, user):
        """
        Validate that the user has at least one Keycloak openimis_roles attribute
        that matches an existing role in tblRole.
        """
        if not hasattr(user, '_get_keycloak_roles'):
            raise exceptions.AuthenticationFailed("KEYCLOAK_ROLE_VALIDATION_FAILED: No Keycloak integration")
            
        kc_roles = user._get_keycloak_roles()
        if not kc_roles:
            logger.warning(f"User {user.username} has no openimis_roles attribute in Keycloak")
            raise exceptions.AuthenticationFailed("KEYCLOAK_ROLE_VALIDATION_FAILED: No openimis_roles attribute found")
        
        # Check if any Keycloak role exists in tblRole
        if not Role.objects.filter(name__in=kc_roles, validity_to__isnull=True).exists():
            logger.warning(f"User {user.username} has Keycloak roles {kc_roles} but none exist in tblRole")
            raise exceptions.AuthenticationFailed("KEYCLOAK_ROLE_VALIDATION_FAILED: No valid roles found in database")

    def validate_opensearch_access(self, user):
        """
        Validate that the user has opensearch_access="true" attribute in Keycloak.
        """
        if not hasattr(user, '_get_keycloak_opensearch_access'):
            raise exceptions.AuthenticationFailed("OPENSEARCH_ACCESS_DENIED: No Keycloak integration")
            
        if not user._get_keycloak_opensearch_access():
            logger.warning(f"User {user.username} has no opensearch_access attribute or it's not set to 'true' in Keycloak")
            raise exceptions.AuthenticationFailed("OPENSEARCH_ACCESS_DENIED: No opensearch_access attribute or not set to 'true'")
