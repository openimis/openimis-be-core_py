import logging
import re
from django.conf import settings
from django.contrib.auth import authenticate
from django.http import JsonResponse
from core.keycloak_auth import KeycloakAuthenticationBackend

logger = logging.getLogger(__name__)


class KeycloakJWTMiddleware:
    """
    Middleware to handle Keycloak JWT authentication for OpenIMIS
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.keycloak_backend = KeycloakAuthenticationBackend()
        
        # Paths that should be excluded from Keycloak auth
        self.exclude_paths = [
            r'^/api/graphql$',  # Allow existing GraphQL auth
            r'^/admin/',
            r'^/static/',
            r'^/media/',
            r'^/keycloak/',
        ]

    def __call__(self, request):
        # Skip Keycloak auth if disabled
        if not getattr(settings, 'KEYCLOAK_ENABLED', False):
            return self.get_response(request)
        
        # Skip for excluded paths
        if self._should_exclude_path(request.path):
            return self.get_response(request)
        
        # Process Keycloak authentication
        self._process_keycloak_auth(request)
        
        response = self.get_response(request)
        return response

    def _should_exclude_path(self, path):
        """
        Check if path should be excluded from Keycloak authentication
        """
        for pattern in self.exclude_paths:
            if re.match(pattern, path):
                return True
        return False

    def _process_keycloak_auth(self, request):
        """
        Process Keycloak JWT token from request
        """
        try:
            # Extract JWT token from Authorization header
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                
                # Try to authenticate with Keycloak token
                user = self.keycloak_backend.authenticate(
                    request, 
                    keycloak_token=token
                )
                
                if user:
                    request.user = user
                    logger.debug(f"Keycloak auth successful for user: {user.username}")
                else:
                    logger.debug("Keycloak auth failed - invalid token")
                    
        except Exception as e:
            logger.error(f"Keycloak middleware error: {e}")


class KeycloakCallbackMiddleware:
    """
    Middleware to handle Keycloak callback and redirect
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle Keycloak callback
        if request.path == '/keycloak/callback' and request.method == 'GET':
            return self._handle_keycloak_callback(request)
        
        return self.get_response(request)

    def _handle_keycloak_callback(self, request):
        """
        Handle Keycloak callback with authorization code
        """
        try:
            # Get authorization code from query parameters
            auth_code = request.GET.get('code')
            if not auth_code:
                return JsonResponse({'error': 'No authorization code provided'}, status=400)
            
            # Exchange code for token (this would be handled by frontend)
            # For now, return success and let frontend handle the token exchange
            return JsonResponse({
                'status': 'success',
                'message': 'Keycloak callback received',
                'code': auth_code
            })
            
        except Exception as e:
            logger.error(f"Keycloak callback error: {e}")
            return JsonResponse({'error': 'Authentication failed'}, status=500)