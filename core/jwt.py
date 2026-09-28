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
