from rest_framework.authentication import BaseAuthentication
from graphql.error import GraphQLError
from django.core.exceptions import PermissionDenied
from rest_framework.exceptions import Throttled
from rest_framework import exceptions
from graphql_jwt.utils import get_credentials
from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.shortcuts import get_user_by_token
from graphql_jwt.backends import JSONWebTokenBackend as BaseJSONWebTokenBackend
from core.apps import CoreConfig
from core.utils import handle_impersonation
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
            except PermissionDenied as exc:
                raise exceptions.AuthenticationFailed(str(exc)) from exc
            
            else:
                if CoreConfig.is_valid_health_facility_contract_required:
                    if not (
                        hasattr(user, "health_facility")
                        and hasattr(user.health_facility, "contract_end_date")
                        and user.health_facility.contract_end_date > date.today()
                    ):
                        raise exceptions.AuthenticationFailed("HF_CONTRACT_INVALID")

            # Use shared utility for impersonation handling (ensures clearing and setting
            # of thread locals on every call, fixing the subsequent calls bug)
            effective_user = handle_impersonation(request, user)
            return effective_user, None

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
    """
    Custom backend extending graphql_jwt one to call the shared handle_impersonation utility.
    This ensures impersonation logic runs for GraphQL paths (where JSONWebTokenBackend is used by the middleware).
    Handles the cache and subsequent calls via the utility + ClearUserContextMiddleware.
    """
    def authenticate(self, request=None, **kwargs):
        try:
            user = super().authenticate(request=request, **kwargs)
            if user is None or request is None:
                # for login request
                return None
        # handle_impersonation will check header, validate, set locals (original/current), and return effective user
        # This addresses recursion notes by using the request from context
            return handle_impersonation(request, user)
        except exceptions.AuthenticationFailed as e:
            raise GraphQLError(
                "INCORRECT_CREDENTIALS",
                extensions={"code": "UNAUTHENTICATED", "message":str(e)}
            )
        except Throttled as e:
            raise GraphQLError(
                "TOO_MANY_REQUEST",
                extensions={
                    "code": "THROTTLED",
                    "rate": settings.RATELIMIT_RATE,
                }
            )
        except PermissionDenied as e:    
            raise GraphQLError(
                "NO_PERMISSION",
                extensions={"code": "FORBIDDEN", "message":str(e)}
            )
            


         
