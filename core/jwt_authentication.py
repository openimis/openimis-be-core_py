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
