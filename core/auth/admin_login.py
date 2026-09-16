"""The Django admin's login form, replaced by a redirect to the frontend's.

AdminSite.login takes a password and opens a session, and that session
authenticates the REST API too - SessionAuthentication is in
DEFAULT_AUTHENTICATION_CLASSES and stays there deliberately. So an enrolled
administrator would log in there on the password alone, and administrators are
who the second factor is for.

The form is removed rather than grown: core.services.open_admin_session already
opens the admin's session once the whole login flow, second factor included,
has passed, so the admin needs no login of its own. django_otp.admin's
OTPAdminSite is the alternative not taken - it is a second login form with its
own enforcement decision, and that decision belongs in core.auth.login.
"""

from django.conf import settings
from django.shortcuts import redirect


def admin_login_redirect(request):
    """Send an unauthenticated admin visitor to the frontend login.

    Root-relative on purpose. settings.FRONTEND_URL is built from SITE_URL,
    which is empty unless a deployment sets it, and then FRONTEND_URL reads
    "http:///front" - not a Location header worth emitting. The admin and the
    frontend are same-origin in the reference deployment, so a relative path is
    both correct and proxy-safe.

    `next` is dropped: the frontend login has no return-to, and it lands on the
    app rather than back here.
    """
    # Stripped, not interpolated raw: SITE_FRONT is an operator-set string and
    # a leading slash would make this "//front/login" - scheme-relative, so the
    # browser leaves for a host called "front". SITE_ROOT and SITE_URL
    # normalise for the same reason.
    front = getattr(settings, "SITE_FRONT", "front").strip("/")
    return redirect(f"/{front}/login")
