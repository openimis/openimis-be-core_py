from .jwt import jwt_decode_user_key

from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions
from graphql_jwt.utils import get_credentials
from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.shortcuts import get_user_by_token

import jwt
import logging

logger = logging.getLogger(__file__)


class JWTAuthentication(BaseAuthentication):
    """
    class to obtain token from header if it is provided
    and verify if this is correct/valid token
    """

    def authenticate(self, request):
        token = get_credentials(request)
        if not token:
            return

        # Do not pass context to avoid to try to get user from request to get his private key.
        try:
            user = get_user_by_token(token)
        except (jwt.PyJWTError, JSONWebTokenError) as exc:
            raise exceptions.AuthenticationFailed(str(exc)) from exc

        return user, None

    def enforce_csrf(self, request):
        return  # To not perform the csrf during checking auth header
