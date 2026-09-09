from calendar import timegm

import jwt
from graphql_jwt.settings import jwt_settings
from graphql_jwt.signals import token_issued
from django.utils import timezone
from django.dispatch import receiver
import logging
import uuid
from datetime import datetime
from core.auth import decode as auth_decode
from core.models import InteractiveUser

logger = logging.getLogger(__file__)


@receiver(token_issued)
def on_token_issued(sender, request, user, **kwargs):
    # Store the date on which the user got the auth token
    if user.i_user:
        user.i_user.last_login = timezone.now()
        user.i_user.save()


def jwt_encode_user_key(payload, context=None):
    payload["jti"] = str(uuid.uuid4())
    payload["nbf"] = timegm(datetime.utcnow().utctimetuple())

    token = jwt.encode(
        payload,
        get_jwt_key(encode=True, context=context, payload=payload),
        algorithm=jwt_settings.JWT_ALGORITHM,
    )
    # JWT module after 1.7 does the encoding, introducing some conflicts in graphql-jwt, let's support both
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def jwt_decode_user_key(token, context=None):
    # Kept as the configured JWT_DECODE_HANDLER so this module stays
    # decode-compatible with an assembly that has not been updated.
    return auth_decode(token, context)


def get_jwt_key(encode=True, context=None, payload=None):
    user_key = extract_private_key_from_context(context)
    if user_key is None and payload is not None:
        user_key = extract_private_key_from_payload(payload)
    if user_key:
        return user_key

    if encode:
        return (
            getattr(jwt_settings, "JWT_PRIVATE_KEY", None)
            or jwt_settings.JWT_SECRET_KEY
        )
    else:
        return (
            getattr(jwt_settings, "JWT_PUBLIC_KEY", None) or jwt_settings.JWT_SECRET_KEY
        )


def extract_private_key_from_payload(payload):
    # Get user private key from payload. This covers the refresh token mutation

    if "username" in payload:
        user = InteractiveUser.objects.get(
            login_name=payload["username"],
            *InteractiveUser.filter_validity()
        )
        if user:
            return user.private_key


def extract_private_key_from_context(context):
    if (
        context
        and context.user
        and hasattr(context.user, "i_user")
        and hasattr(context.user.i_user, "private_key")
    ):
        return context.user.i_user.private_key
    return None
