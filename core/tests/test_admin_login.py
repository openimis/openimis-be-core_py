from django.test import RequestFactory, TestCase, override_settings

from core.auth.admin_login import admin_login_redirect


class AdminLoginRedirectTest(TestCase):
    def test_it_redirects_to_the_frontend_login(self):
        response = admin_login_redirect(RequestFactory().get("/api/admin/login/"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/front/login")

    @override_settings(SITE_FRONT="portal")
    def test_it_honours_the_deployment_front_path(self):
        response = admin_login_redirect(RequestFactory().get("/api/admin/login/"))
        self.assertEqual(response["Location"], "/portal/login")

    def test_a_misconfigured_front_path_stays_same_origin(self):
        # "//front/login" is scheme-relative: the browser leaves for a host
        # called "front". SITE_ROOT and SITE_URL both normalise for this
        # reason, and this is an unauthenticated redirect.
        for configured in ("/front", "front/", "/front/"):
            with self.subTest(site_front=configured), override_settings(
                SITE_FRONT=configured
            ):
                response = admin_login_redirect(
                    RequestFactory().get("/api/admin/login/")
                )
                self.assertEqual(response["Location"], "/front/login")

    def test_it_is_relative_so_an_unset_site_url_cannot_break_it(self):
        # settings.FRONTEND_URL is "http:///front" whenever SITE_URL is unset,
        # which is the default. Nothing here may be built from it.
        response = admin_login_redirect(RequestFactory().get("/api/admin/login/"))
        self.assertTrue(response["Location"].startswith("/"))
