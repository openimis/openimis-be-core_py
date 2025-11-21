import logging
import jwt
import requests
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from core.models import InteractiveUser, User

logger = logging.getLogger(__name__)

User = get_user_model()


class KeycloakAuthenticationBackend(BaseBackend):
    """
    Keycloak authentication backend for OpenIMIS.
    Handles JWT token verification and user provisioning.
    """

    def authenticate(self, request, username=None, password=None, keycloak_token=None, **kwargs):
        """
        Authenticate user with Keycloak JWT token or fallback to username/password
        """
        if not getattr(settings, 'KEYCLOAK_ENABLED', False):
            return None

        if keycloak_token:
            return self._authenticate_with_token(keycloak_token)
        elif username and password:
            return self._authenticate_with_credentials(username, password)
        
        return None

    def _authenticate_with_token(self, token):
        """
        Authenticate using Keycloak JWT token
        """
        try:
            logger.info("=== TOKEN AUTHENTICATION DEBUG ===")
            logger.info("Starting token authentication with token length: %s", len(token) if token else 0)
            
            # Verify and decode the JWT token
            user_info = self._verify_keycloak_token(token)
            logger.info("Token verification result: %s", bool(user_info))
            
            if not user_info:
                logger.error("Token verification failed - no user info returned")
                return None

            logger.info("User info from token: %s", user_info)
            
            # Get or create user based on Keycloak user info
            user = self._get_or_create_user(user_info)
            logger.info("User creation/retrieval result: %s", bool(user))
            # MAJ du champ last_login de l'InteractiveUser
            from django.utils import timezone
            if user and hasattr(user, 'i_user') and user.i_user:
                user.i_user.last_login = timezone.now()
                user.i_user.save(update_fields=["last_login"])
            # Try to trigger role sync exactly like login signal handler.
            # Some authentication flows (token-based) don't call django.login(), so user_logged_in
            # may not be emitted. Call the sync handler directly in a safe way.
            try:
                # Lazy import to avoid circular imports at module load
                from core.keycloak_signals import sync_keycloak_roles_on_login
                # Call with sender=self class, request may be None here
                try:
                    sync_keycloak_roles_on_login(sender=self.__class__, request=None, user=user)
                except TypeError:
                    # Fallback if signature differs
                    sync_keycloak_roles_on_login(None, None, user)
            except Exception as e:
                logger.warning(f"Failed to run keycloak role sync on auth path: {e}")

            return user

        except Exception as e:
            logger.error(f"Keycloak token authentication failed: {e}", exc_info=True)
            return None

    def _authenticate_with_credentials(self, username, password):
        """
        Authenticate using username/password via Keycloak
        """
        try:
            token = self._get_keycloak_token(username, password)
            if token:
                return self._authenticate_with_token(token['access_token'])
        except Exception as e:
            logger.error(f"Keycloak credentials authentication failed: {e}")
        
        return None

    def _verify_keycloak_token(self, token):
        """
        Verify JWT token with Keycloak public key
        """
        try:
            logger.info("=== TOKEN VERIFICATION DEBUG ===")
            logger.info("Starting token verification")
            logger.info("KEYCLOAK_SERVER_URL: %s", getattr(settings, 'KEYCLOAK_SERVER_URL', 'NOT_SET'))
            logger.info("KEYCLOAK_REALM: %s", getattr(settings, 'KEYCLOAK_REALM', 'NOT_SET'))
            logger.info("KEYCLOAK_CLIENT_ID: %s", getattr(settings, 'KEYCLOAK_CLIENT_ID', 'NOT_SET'))
            
            # Get Keycloak public key
            logger.info("Getting Keycloak public key...")
            public_key = self._get_keycloak_public_key()
            logger.info("Public key retrieved: %s", bool(public_key))
            
            # Decode and verify token
            logger.info("Decoding JWT token...")
            expected_issuer = f"{settings.KEYCLOAK_SERVER_URL}/realms/{settings.KEYCLOAK_REALM}"
            
            logger.info("Expected issuer: %s", expected_issuer)
            
            # Try to decode without audience first, as some Keycloak configurations don't include it
            try:
                decoded_token = jwt.decode(
                    token,
                    public_key,
                    algorithms=['RS256'],
                    issuer=expected_issuer,
                    options={"verify_aud": False}  # Skip audience verification
                )
                logger.info("Token decoded successfully without audience verification. Subject: %s", decoded_token.get('sub'))
            except Exception as e:
                logger.info("Failed without audience verification, trying with audience...")
                # Fallback to audience verification if needed
                expected_audience = settings.KEYCLOAK_CLIENT_ID
                logger.info("Expected audience: %s", expected_audience)
                
                decoded_token = jwt.decode(
                    token,
                    public_key,
                    algorithms=['RS256'],
                    audience=expected_audience,
                    issuer=expected_issuer
                )
                logger.info("Token decoded successfully with audience verification. Subject: %s", decoded_token.get('sub'))
            
            return decoded_token
            
        except jwt.ExpiredSignatureError:
            logger.warning("Keycloak token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid Keycloak token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}", exc_info=True)
            return None

    def _get_keycloak_public_key(self):
        """
        Retrieve Keycloak realm public key
        """
        try:
            realm_url = f"{settings.KEYCLOAK_SERVER_URL}/realms/{settings.KEYCLOAK_REALM}"
            response = requests.get(realm_url)
            response.raise_for_status()
            
            realm_info = response.json()
            public_key = f"-----BEGIN PUBLIC KEY-----\n{realm_info['public_key']}\n-----END PUBLIC KEY-----"
            return public_key
            
        except Exception as e:
            logger.error(f"Failed to get Keycloak public key: {e}")
            raise

    def _get_keycloak_token(self, username, password):
        """
        Get access token from Keycloak using username/password
        """
        try:
            token_url = f"{settings.KEYCLOAK_SERVER_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
            
            data = {
                'grant_type': 'password',
                'client_id': settings.KEYCLOAK_CLIENT_ID,
                'username': username,
                'password': password,
            }
            
            if getattr(settings, 'KEYCLOAK_CLIENT_SECRET'):
                data['client_secret'] = settings.KEYCLOAK_CLIENT_SECRET
            
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Failed to get Keycloak token: {e}")
            return None

    def _get_or_create_user(self, keycloak_user_info):
        """
        Get or create OpenIMIS user based on Keycloak user info
        """
        try:
            # Extract username from Keycloak token
            username = keycloak_user_info.get(
                getattr(settings, 'KEYCLOAK_USER_MAPPING', {}).get('username', 'preferred_username')
            )
            if not username:
                logger.error("No username found in Keycloak token")
                return None

            # Try to find existing user
            try:
                user = User.objects.get(username=username)
                self._update_user_from_keycloak(user, keycloak_user_info)
                return user
            except User.DoesNotExist:
                pass

            # Try to find existing InteractiveUser
            try:
                i_user = InteractiveUser.objects.get(
                    login_name=username,
                    validity_to__isnull=True
                )
                # Create Core User if it doesn't exist
                try:
                    user = User.objects.get(i_user=i_user)
                except User.DoesNotExist:
                    user = User.objects.create(
                        username=username,
                        i_user=i_user
                    )
                self._update_user_from_keycloak(user, keycloak_user_info)
                return user
            except InteractiveUser.DoesNotExist:
                # --- AUTO-PROVISION USER FROM KEYCLOAK ---
                logger.info(f"Auto-provisioning OpenIMIS user for Keycloak user: {username}")
                # Get info from token or set defaults
                mapping = getattr(settings, 'KEYCLOAK_USER_MAPPING', {})
                email = keycloak_user_info.get(mapping.get('email', 'email'), f"{username}@example.com")
                last_name = keycloak_user_info.get(mapping.get('last_name', 'family_name'), username)
                other_names = keycloak_user_info.get(mapping.get('first_name', 'given_name'), username)
                # Find default language (fallback to first Language object)
                from core.models import Language
                language = Language.objects.filter().first()
                if not language:
                    logger.error("No Language found in DB for InteractiveUser creation")
                    return None
                # Set audit_user_id to 1 (admin) or fallback
                audit_user_id = 2
                # Set default role_id
                role_id = 1023
                # Generate password and private key
                #default_password = keycloak_user_info.get('password', 'KeycloakAutoPassword2025!')
                # Create InteractiveUser
                i_user = InteractiveUser(
                    login_name=username,
                    last_name=last_name or username,
                    other_names=other_names or username,
                    email=email,
                    language=language,
                    audit_user_id=audit_user_id,
                    role_id=role_id
                )
                #i_user.set_password(default_password)
                i_user.save()
                # Create Core User
                user = User.objects.create(
                    username=username,
                    i_user=i_user
                )
                self._update_user_from_keycloak(user, keycloak_user_info)
                logger.info(f"Created new OpenIMIS user for Keycloak user: {username}")
                return user
        except Exception as e:
            logger.error(f"Error getting/creating user: {e}")
            return None

    def _update_user_from_keycloak(self, user, keycloak_user_info):
        """
        Update user info from Keycloak data
        """
        try:
            mapping = settings.KEYCLOAK_USER_MAPPING
            
            if user.i_user:
                # Update InteractiveUser fields if available
                email = keycloak_user_info.get(mapping.get('email', 'email'))
                if email and email != user.i_user.email:
                    user.i_user.email = email
                    user.i_user.save()
                    
        except Exception as e:
            logger.error(f"Error updating user from Keycloak: {e}")

    def get_user(self, user_id):
        """
        Get user by ID (required by Django auth backend interface)
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None