from django.utils.timezone import now
from django_ratelimit.core import is_ratelimited
from rest_framework.exceptions import JsonResponse
from django.conf import settings


class DefaultAxesAttributesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set default values for Django-axes attributes if they're not already set
        if not hasattr(request, 'axes_ip_address'):
            request.axes_ip_address = request.META.get('REMOTE_ADDR', '')
        if not hasattr(request, 'axes_user_agent'):
            request.axes_user_agent = request.META.get('HTTP_USER_AGENT', '')
        if not hasattr(request, 'axes_attempt_time'):
            request.axes_attempt_time = now()

        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if settings.MODE == "PROD":
            response["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
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
        if mode == 'PROD' and request.path == '/api/graphql':
            rate_limited = is_ratelimited(
                request=request,
                group=group,
                key=key,
                rate=rate,
                method=is_ratelimited.ALL,
                increment=True
            )
            if rate_limited:
                return JsonResponse({'detail': 'Rate limit exceeded'}, status=429)
        response = self.get_response(request)
        return response
