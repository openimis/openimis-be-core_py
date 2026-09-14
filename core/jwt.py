from graphql_jwt.settings import jwt_settings
from graphql_jwt.signals import token_issued
from django.db import transaction
from django.utils import timezone
from django.dispatch import receiver
import logging
from core.auth import decode as auth_decode
from core.auth.encode import encode as auth_encode
from core.models import InteractiveUser

logger = logging.getLogger(__file__)


@receiver(token_issued)
def on_token_issued(sender, request, user, **kwargs):
    # Store the date on which the user got the auth token
    if user.i_user:
        with transaction.atomic():
            i_user = InteractiveUser.locked_from_database(user.i_user.pk)
            i_user.last_login = timezone.now()
            i_user.save()


def jwt_encode_user_key(payload, context=None):
    # Kept as the configured JWT_ENCODE_HANDLER, and imported directly by
    # api_fhir_r4's login view, so the name and signature outlive the per-user
    # key this module used to resolve.
    return auth_encode(payload, context)


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
