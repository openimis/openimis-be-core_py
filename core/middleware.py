import logging
from django.utils.timezone import now
from django_ratelimit.core import is_ratelimited
from rest_framework.exceptions import JsonResponse
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.middleware import get_user
from django.contrib.auth.models import AnonymousUser
from graphql_jwt.middleware import JSONWebTokenMiddleware, _authenticate
from graphql_jwt.settings import jwt_settings
from graphql_jwt.utils import get_token_argument
from core.utils import (
    clear_current_user,
    clear_original_user,
    clear_history_context,
    handle_impersonation,
)


logger = logging.getLogger(__name__)


class ClearUserContextMiddleware:
    """
    Middleware to clear the thread-local user context (current_user and original_user)
    at the start of every request. This prevents state leakage across requests on reused
    threads in production, fixing the impersonation bug for subsequent calls.
    Also supports loading persistent impersonation state from session to avoid
    needing the header on every request.
    Must be placed early in the MIDDLEWARE list (after SessionMiddleware).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_current_user()
        clear_original_user()
        clear_history_context()
        # Support for persistent impersonation state via session (to support
        # "subsequent calls" without header every time per user feedback)
        if (
            hasattr(request, "session")
            and "impersonated_user_uuid" in request.session
            and not request.META.get("HTTP_X_IMPERSONATE_USER")
        ):
            request.META["HTTP_X_IMPERSONATE_USER"] = request.session[
                "impersonated_user_uuid"
            ]
            logger.info(
                "Loaded persistent impersonation from session for user %s",
                request.session["impersonated_user_uuid"],
            )
        return self.get_response(request)


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
            response["Permissions-Policy"] = "geolocation=(), microphone()"

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


class CustomJSONWebTokenMiddleware(JSONWebTokenMiddleware):
    """
    Custom middleware extending graphql_jwt's JSONWebTokenMiddleware to handle
    impersonation header. When the impersonation header is present we ensure
    the effective (impersonated) user is used for permissions and thread-locals,
    but we reuse an already-resolved base user (from context or request.user)
    and the object cache (cs_User_*) for both the original and impersonated User.
    Full re-auth is only done when no user has been established yet for the
    request/operation (keeps "auth of user" while avoiding repeated "dev"
    username/DB lookups on every resolver). Also integrates with the custom
    backend for handle_impersonation.
    """

    def resolve(self, next, root, info, **kwargs):
        context = info.context
        # Get a request-like object for .META (GraphQL context may wrap the real request)
        request = context
        if hasattr(context, "request"):
            request = context.request

        # Get impersonation header (context in GraphQL can be request or have META)
        impersonate_header = None
        if hasattr(context, "META"):
            impersonate_header = context.META.get("HTTP_X_IMPERSONATE_USER")
        elif hasattr(request, "META"):
            impersonate_header = request.META.get("HTTP_X_IMPERSONATE_USER")

        token_argument = get_token_argument(context, **kwargs)

        # === Quick win for excessive user reloads ===
        base_user = getattr(context, "user", None)
        if not base_user or getattr(base_user, "is_anonymous", False):
            if hasattr(request, "user") and not getattr(request.user, "is_anonymous", False):
                base_user = request.user

        if base_user and not getattr(base_user, "is_anonymous", False):
            if impersonate_header and not getattr(context, "_impersonation_applied", False):
                # Re-apply impersonation (cheap when users are cached; ensures
                # impersonated identity + perms are active for this resolve)
                effective_user = handle_impersonation(request, base_user)
                context.user = effective_user
                setattr(context, "_impersonation_applied", True)
            elif not impersonate_header:
                context.user = base_user
            return next(root, info, **kwargs)

        # No base user yet → fall back to original (full) authentication logic.
        # This is the "auth" step that resolves the bearer of the JWT ("dev").
        if (
            jwt_settings.JWT_ALLOW_ARGUMENT
            and token_argument is None
            and not impersonate_header
        ):
            user = self.cached_authentication.parent(info.path)

            if user is not None:
                context.user = user

            elif hasattr(context, "user"):
                if hasattr(context, "session"):
                    context.user = get_user(context)
                    self.cached_authentication.insert(info.path, context.user)
                else:
                    context.user = AnonymousUser()

        if (
            (_authenticate(context) or token_argument is not None or impersonate_header)
            and self.authenticate_context(info, **kwargs)
        ):

            user = authenticate(request=context, **kwargs)

            if user is not None:
                if impersonate_header:
                    # This is where the impersonated user (with its perms) becomes
                    # the effective context.user. handle_impersonation also sets
                    # the thread locals used by get_current_user().
                    user = handle_impersonation(request, user)
                context.user = user

                if jwt_settings.JWT_ALLOW_ARGUMENT and not impersonate_header:
                    self.cached_authentication.insert(info.path, user)

            if impersonate_header:
                setattr(context, "_impersonation_applied", True)

        return next(root, info, **kwargs)
