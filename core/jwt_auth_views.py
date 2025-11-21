"""
Streamlined OpenSearch JWT authentication endpoint for nginx auth_request.
"""

from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from core.jwt_authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
import logging

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "HEAD"])
def opensearch_jwt_auth_check(request):
    """
    Validate JWT + opensearch_access for OpenSearch Dashboards.
    Returns 200 if authorized, 403 if not.
    """
    try:
        auth = JWTAuthentication()
        result = auth.authenticate(request)
        
        if not result:
            return HttpResponseForbidden("Authentication required")
        
        user, _ = result
        if not user or not user.is_active:
            return HttpResponseForbidden("User not active")
        
        # Validate OpenSearch access
        auth.validate_opensearch_access(user)
        return HttpResponse("OK")
        
    except AuthenticationFailed as e:
        logger.debug(f"OpenSearch auth failed for user: {e}")
        return HttpResponseForbidden("Access denied")
    except Exception as e:
        logger.error(f"OpenSearch auth error: {e}")
        return HttpResponseForbidden("Authentication error")