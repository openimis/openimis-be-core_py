from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import Throttled
from rest_framework import exceptions
from graphql import GraphQLError
from graphql_jwt.utils import get_credentials
from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.backends import JSONWebTokenBackend as BaseJSONWebTokenBackend
from graphql_jwt.shortcuts import get_user_by_token
from core.apps import CoreConfig
from core.utils import ImpersonationDenied, handle_impersonation
from django.conf import settings
from django_ratelimit.core import is_ratelimited

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
                    if not (
                        hasattr(user, "health_facility")
                        and hasattr(user.health_facility, "contract_end_date")
                        and user.health_facility.contract_end_date > date.today()
                    ):
                        raise exceptions.AuthenticationFailed("HF_CONTRACT_INVALID")
            # Sets the current/original user thread locals and applies the
            # X-Impersonate-User header when this instance allows it.
            return handle_impersonation(request, user), None

    def enforce_csrf(self, request):
        return  # To not perform the csrf during checking auth header

    @staticmethod
    def check_rate_limit(request) -> None:
        group = settings.RATELIMIT_GROUP
        key = settings.RATELIMIT_KEY
        rate = settings.RATELIMIT_RATE
        mode = settings.MODE

        if mode == "PROD" and is_ratelimited(
            request=request,
            group=group,
            fn=None,
            key=key,
            rate=rate,
            method=is_ratelimited.ALL,
            increment=True,
        ):
            raise Throttled(detail="Rate limit exceeded")


class JSONWebTokenBackend(BaseJSONWebTokenBackend):
    """graphql_jwt backend that additionally resolves impersonation.

    Only handle_impersonation is wrapped: authentication itself keeps raising
    whatever graphql_jwt raises, so requests without the impersonation header
    behave exactly as they do without this backend.
    """

    def authenticate(self, request=None, **kwargs):
        user = super().authenticate(request=request, **kwargs)
        if user is None or request is None:
            # No credentials, or a login request that carries no request context.
            return None
        try:
            return handle_impersonation(request, user)
        except ImpersonationDenied as exc:
            # Django's authenticate() swallows PermissionDenied -- it stops the
            # backend chain and returns None -- which would silently drop the
            # refusal. GraphQLError propagates, and its message is what the
            # frontend matches on to stop impersonating.
            raise GraphQLError(str(exc), extensions={"code": "FORBIDDEN"}) from exc
