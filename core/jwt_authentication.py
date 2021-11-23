from .jwt import jwt_decode_user_key

from django.apps import apps
from django.contrib.auth import authenticate
from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions

import base64
import jwt
import logging
import os

logger = logging.getLogger(__file__)


class JWTAuthentication(BaseAuthentication):
    """
        class to obtain token from header if it is provided
        and verify if this is correct/valid token
    """

    def authenticate(self, request):
        authorization_header = request.headers.get('Authorization')
        if not authorization_header:
            return None
        payload = None
        is_remote_user_auth = os.getenv('REMOTE_USER_AUTHENTICATION', 'False')
        if authorization_header.lower().startswith('bearer '):
            bearer, access_token, *extra_words = authorization_header.split(' ')
            if len(extra_words) > 0:
                raise exceptions.AuthenticationFailed("Improper structure of token")
            try:
                payload = jwt_decode_user_key(token=access_token)
            except jwt.DecodeError:
                raise exceptions.AuthenticationFailed('Error on decoding token')
            except jwt.ExpiredSignatureError:
                raise exceptions.AuthenticationFailed('Access_token expired')
            except IndexError:
                raise exceptions.AuthenticationFailed('Token prefix missing')
            user = None
            if payload:
                user_class = apps.get_model("core", "User")
                user = user_class.objects \
                    .filter(username=payload.get("username")) \
                    .only("i_user__private_key") \
                    .first()
            if user is None:
                raise exceptions.AuthenticationFailed('User inactive or deleted/not existed.')
            if not user.is_active:
                raise exceptions.AuthenticationFailed('User is inactive')
        elif is_remote_user_auth.lower() == 'true':
            # support for basic auth when we have in backend 'api' instead of 'iapi'
            if authorization_header.lower().startswith('basic'):
                if self._check_basic_auth_user_exist(authorization_header):
                    return None
            else:
                raise exceptions.AuthenticationFailed("Basic auth error: there is no basic header")
        else:
            raise exceptions.AuthenticationFailed("Missing 'Bearer' prefix")

        self.enforce_csrf(request)

        return user, None

    def enforce_csrf(self, request):
        return  # To not perform the csrf during checking auth header

    def _check_basic_auth_user_exist(self, auth_header):
        """when we have 'api' root instead of 'iapi' - check user by using basic auth"""
        token_type, _, credentials = auth_header.partition(' ')
        # get username from base token
        username = base64.b64decode(credentials).decode("utf8").split(':', 1)[0]
        # check if user exists in db
        user_class = apps.get_model("core", "User")
        user = user_class.objects.filter(username=username).first()
        if user:
            return True
        else:
            raise exceptions.AuthenticationFailed("Basic auth error: such user doesn't exist")
