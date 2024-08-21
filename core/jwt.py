from calendar import timegm

import jwt
from graphql_jwt.settings import jwt_settings
from graphql_jwt.signals import token_issued
from django.apps import apps
from django.utils import timezone
from django.dispatch import receiver
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__file__)


@receiver(token_issued)
def on_token_issued(sender, request, user, **kwargs):
    # Store the date on which the user got the auth token
    user.last_login = timezone.now()
    user.save()
    pass


def jwt_encode_user_key(payload, context=None):
    payload['jti'] = str(uuid.uuid4())
    payload['nbf'] = timegm(datetime.utcnow().utctimetuple())

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
    # First decode the token without validating it, so we can extract the username
    not_validated = jwt.decode(
        token,
        get_jwt_key(encode=False, context=context),
        options={
            'verify_exp': jwt_settings.JWT_VERIFY_EXPIRATION,
            'verify_aud': jwt_settings.JWT_AUDIENCE is not None,
            'verify_signature': False,
        },
        leeway=jwt_settings.JWT_LEEWAY,
        audience=jwt_settings.JWT_AUDIENCE,
        issuer=jwt_settings.JWT_ISSUER,
        algorithms=[jwt_settings.JWT_ALGORITHM],
    )
    if not_validated and not_validated.get("username"):
        user_class = apps.get_model("core", "User")
        db_user = user_class.objects \
            .filter(username=not_validated.get("username")) \
            .only("i_user__private_key") \
            .first()
        if db_user and db_user.private_key:
            key = db_user.private_key
        else:
            key = get_jwt_key(encode=False)
    else:
        key = get_jwt_key(encode=False)
    return jwt.decode(
        token,
        key,
        options={
            'verify_exp': jwt_settings.JWT_VERIFY_EXPIRATION,
            'verify_aud': jwt_settings.JWT_AUDIENCE is not None,
            'verify_signature': jwt_settings.JWT_VERIFY,
        },
        leeway=jwt_settings.JWT_LEEWAY,
        audience=jwt_settings.JWT_AUDIENCE,
        issuer=jwt_settings.JWT_ISSUER,
        algorithms=[jwt_settings.JWT_ALGORITHM],
    )


def get_jwt_key(encode=True, context=None, payload=None):
    user_key = extract_private_key_from_context(context)
    if user_key is None and payload is not None:
        user_key = extract_private_key_from_payload(payload)
    if user_key:
        return user_key

    if encode:
        return getattr(jwt_settings, "JWT_PRIVATE_KEY", jwt_settings.JWT_SECRET_KEY)
    else:
        return getattr(jwt_settings, "JWT_PUBLIC_KEY", jwt_settings.JWT_SECRET_KEY)


def extract_private_key_from_payload(payload):
    # Get user private key from payload. This covers the refresh token mutation
    from core.models import User

    if "username" in payload:
        return User.objects.get(username=payload["username"]).private_key


def extract_private_key_from_context(context):
    if context and context.user and hasattr(context.user, "private_key"):
        return context.user.private_key
    return None
