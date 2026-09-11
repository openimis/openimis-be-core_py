import logging
from django.contrib.auth import authenticate
from django.utils.timezone import now
from django_ratelimit.core import is_ratelimited
from rest_framework.exceptions import JsonResponse
from django.conf import settings
from graphql_jwt.middleware import JSONWebTokenMiddleware

from core.utils import (
    impersonation_target_id,
    clear_current_user,
    clear_history_context,
    clear_original_user,
    get_original_user,
)


logger = logging.getLogger(__name__)


class ClearUserContextMiddleware:
    """Reset the thread-local user context at the start of every request.

    Gunicorn and the dev server both reuse threads between requests, so without
    this the current/original user (and the simple-history request) set by the
    previous request stay visible to the next one -- which is how an
    impersonation would bleed into a later, unrelated call.

    Must sit early in MIDDLEWARE, after SessionMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_current_user()
        clear_original_user()
        clear_history_context()
        return self.get_response(request)


class CustomJSONWebTokenMiddleware(JSONWebTokenMiddleware):
    """graphql_jwt authenticates only while the context has no user yet.

    Once a user is on the context -- cached per path, or resolved from a Django
    session -- the parent skips authenticate(), and with it the impersonation
    handling in core.jwt_authentication.JSONWebTokenBackend. So a request
    carrying X-Impersonate-User authenticates explicitly instead.

    get_original_user() is the "already applied" marker: ClearUserContextMiddleware
    empties it per request, and handle_impersonation fills it in, so only the
    first resolved field of a request pays for the extra authenticate() call.
    The impersonated user is deliberately never written to the parent's
    per-path cache.
    """

    def resolve(self, next, root, info, **kwargs):
        context = info.context

        if (
            impersonation_target_id(context)
            and get_original_user() is None
            and self.authenticate_context(info, **kwargs)
        ):
            # Raises (as a GraphQLError) when this instance has impersonation
            # disabled, the caller is not a superuser, or the target is unknown.
            user = authenticate(request=context, **kwargs)
            if user is not None:
                context.user = user
            return next(root, info, **kwargs)

        return super().resolve(next, root, info, **kwargs)


class DefaultAxesAttributesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set default values for Django-axes attributes if they're not already set
        if not hasattr(request, "axes_ip_address"):
            request.axes_ip_address = request.META.get("REMOTE_ADDR", "")
        if not hasattr(request, "axes_user_agent"):
            request.axes_user_agent = request.META.get("HTTP_USER_AGENT", "")
        if not hasattr(request, "axes_attempt_time"):
            request.axes_attempt_time = now()

        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if settings.MODE == "PROD":
            response["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
            response["Content-Security-Policy"] = "default-src 'self';"
            response["X-Frame-Options"] = "DENY"
            response["X-Content-Type-Options"] = "nosniff"
            response["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response["Permissions-Policy"] = "geolocation=(), microphone=()"

        return response


class GraphQLRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        group = settings.RATELIMIT_GROUP
        key = settings.RATELIMIT_KEY
        rate = settings.RATELIMIT_RATE
        mode = settings.MODE
        if mode == "PROD" and request.path == "/api/graphql":
            rate_limited = is_ratelimited(
                request=request,
                group=group,
                key=key,
                rate=rate,
                method=is_ratelimited.ALL,
                increment=True,
            )
            if rate_limited:
                return JsonResponse({"detail": "Rate limit exceeded"}, status=429)
        response = self.get_response(request)
        return response


class AdminLogoutMiddleware:
    """
    Middleware to clear all user sessions when they log out from Django Admin.
    """

    LOGOUT_URL = f"/{settings.SITE_ROOT()}admin/logout/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith(self.LOGOUT_URL):
            response.delete_cookie("JWT")
            logger.info("Cleared all sessions after admin panel logout")

        return response
