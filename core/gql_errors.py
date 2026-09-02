from django.utils.translation import gettext_lazy as _
from graphql_jwt.exceptions import JSONWebTokenError


class AuthenticationRequired(JSONWebTokenError):
    # Subclassing JSONWebTokenError makes OpenIMISGraphQLView return 401; Django's
    # PermissionDenied stays 200. Distinct "unauthenticated" message separates
    # authN from the "unauthorized" authZ (has_perms) failures.
    default_message = _("unauthenticated")
