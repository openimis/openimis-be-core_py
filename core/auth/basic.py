"""HTTP Basic, with the second factor the login flow cannot reach.

BasicAuthentication takes a password on every request, so there is no login
step for core.auth.login to sit in: an enrolled user's password alone would
authenticate every REST and FHIR view. This refuses that, through the same
predicate the login flow asks, so the enrolment question stays in one place.

A user who owes nothing - no confirmed device, and a policy that does not bind
them - is untouched. A technical account is outside every policy while it is
neither staff nor superuser, which is what keeps the integrations that
authenticate with one working.
"""

from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.auth.login import SECOND_FACTOR_REQUIRED, mfa_required


class SecondFactorBasicAuthentication(BasicAuthentication):
    """Basic auth that refuses a user who owes a second factor."""

    def authenticate_credentials(self, userid, password, request=None):
        # After the credentials check, not before: refusing early would answer
        # differently to a wrong password and to an enrolled user, and the
        # header would enumerate who is enrolled.
        user, auth = super().authenticate_credentials(userid, password, request)
        if mfa_required(user):
            # Nothing here can carry a code - the header has two fields. The
            # token flow is where an enrolled user logs in.
            raise AuthenticationFailed(SECOND_FACTOR_REQUIRED)
        return user, auth
