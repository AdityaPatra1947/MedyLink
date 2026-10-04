"""The normal app and local synthetic demo share a host, but not a login."""

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AuthSession, User


PREFIX = "/api/v1/auth/"
PASSWORD = "Cookie-isolation-test-password-294!"
NORMAL = {
    "AUTH_ACCESS_COOKIE_NAME": "access_token",
    "AUTH_REFRESH_COOKIE_NAME": "refresh_token",
    "CSRF_COOKIE_NAME": "csrftoken",
    "SESSION_COOKIE_NAME": "sessionid",
}
SYNTHETIC = {
    "AUTH_ACCESS_COOKIE_NAME": "medylink_synthetic_access_token",
    "AUTH_REFRESH_COOKIE_NAME": "medylink_synthetic_refresh_token",
    "CSRF_COOKIE_NAME": "medylink_synthetic_csrftoken",
    "SESSION_COOKIE_NAME": "medylink_synthetic_sessionid",
}


class CookieIsolationTests(TestCase):
    def setUp(self):
        self.browser = APIClient(enforce_csrf_checks=True)
        self.normal_user = self.make_user("normal@example.com")
        self.synthetic_user = self.make_user("synthetic@example.com")

    def make_user(self, email):
        return User.objects.create_user(
            email=email,
            password=PASSWORD,
            name="Cookie isolation test",
            role="patient",
            email_verified_at=timezone.now(),
        )

    def csrf(self):
        response = self.browser.get(PREFIX + "csrf/")
        self.assertEqual(response.status_code, 200)
        token = response.data["csrfToken"]
        self.browser.credentials(HTTP_X_CSRFTOKEN=token)
        return token

    def login(self, user):
        response = self.browser.post(
            PREFIX + "login/",
            {"email": user.email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response

    def assert_signed_in_as(self, user):
        response = self.browser.get(PREFIX + "me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], str(user.id))

    def test_shared_browser_keeps_independent_login_refresh_and_logout(self):
        with override_settings(**NORMAL):
            normal_csrf = self.csrf()
            self.login(self.normal_user)
            normal_access = self.browser.cookies["access_token"].value
            normal_refresh = self.browser.cookies["refresh_token"].value

        with override_settings(**SYNTHETIC):
            synthetic_csrf = self.csrf()
            response = self.login(self.synthetic_user)
            self.assertEqual(
                set(response.cookies),
                {SYNTHETIC["AUTH_ACCESS_COOKIE_NAME"], SYNTHETIC["AUTH_REFRESH_COOKIE_NAME"]},
            )
            self.assert_signed_in_as(self.synthetic_user)
            self.assertEqual(self.browser.cookies["access_token"].value, normal_access)
            self.assertEqual(self.browser.cookies["refresh_token"].value, normal_refresh)
            previous_refresh = self.browser.cookies[SYNTHETIC["AUTH_REFRESH_COOKIE_NAME"]].value
            refreshed = self.browser.post(PREFIX + "refresh/", {}, format="json")
            self.assertEqual(refreshed.status_code, 200)
            self.assertEqual(refreshed.data["user"]["id"], str(self.synthetic_user.id))
            self.assertNotEqual(
                self.browser.cookies[SYNTHETIC["AUTH_REFRESH_COOKIE_NAME"]].value,
                previous_refresh,
            )
            synthetic_access = self.browser.cookies[SYNTHETIC["AUTH_ACCESS_COOKIE_NAME"]].value
            synthetic_refresh = self.browser.cookies[SYNTHETIC["AUTH_REFRESH_COOKIE_NAME"]].value

        with override_settings(**NORMAL):
            self.browser.credentials(HTTP_X_CSRFTOKEN=normal_csrf)
            self.assert_signed_in_as(self.normal_user)
            self.assertEqual(self.browser.post(PREFIX + "refresh/", {}, format="json").status_code, 200)
            response = self.browser.post(PREFIX + "logout/", {}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.cookies), {"access_token", "refresh_token"})
            self.assertEqual(self.browser.get(PREFIX + "me/").status_code, 401)

        with override_settings(**SYNTHETIC):
            self.browser.credentials(HTTP_X_CSRFTOKEN=synthetic_csrf)
            self.assertEqual(self.browser.cookies[SYNTHETIC["AUTH_ACCESS_COOKIE_NAME"]].value, synthetic_access)
            self.assertEqual(self.browser.cookies[SYNTHETIC["AUTH_REFRESH_COOKIE_NAME"]].value, synthetic_refresh)
            self.assert_signed_in_as(self.synthetic_user)
            response = self.browser.post(PREFIX + "logout/", {}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                set(response.cookies),
                {SYNTHETIC["AUTH_ACCESS_COOKIE_NAME"], SYNTHETIC["AUTH_REFRESH_COOKIE_NAME"]},
            )
            self.assertEqual(self.browser.get(PREFIX + "me/").status_code, 401)
        self.assertFalse(AuthSession.objects.filter(revoked_at__isnull=True).exists())

    def test_other_app_cookies_never_act_as_fallback_credentials(self):
        with override_settings(**NORMAL):
            normal_csrf = self.csrf()
            self.login(self.normal_user)
            normal_access = self.browser.cookies["access_token"].value
            normal_refresh = self.browser.cookies["refresh_token"].value

        with override_settings(**SYNTHETIC):
            self.csrf()
            self.assertEqual(self.browser.get(PREFIX + "me/").status_code, 401)
            self.assertEqual(self.browser.post(PREFIX + "refresh/", {}, format="json").status_code, 401)
            self.assertEqual(self.browser.post(PREFIX + "logout/", {}, format="json").status_code, 200)
            self.assertEqual(self.browser.cookies["access_token"].value, normal_access)
            self.assertEqual(self.browser.cookies["refresh_token"].value, normal_refresh)

        with override_settings(**NORMAL):
            self.browser.credentials(HTTP_X_CSRFTOKEN=normal_csrf)
            self.assert_signed_in_as(self.normal_user)

    def test_each_namespace_requires_its_own_csrf_cookie_and_token(self):
        with override_settings(**NORMAL):
            normal_csrf = self.csrf()

        with override_settings(**SYNTHETIC):
            # A valid normal-app token is insufficient without the demo's cookie.
            data = {"email": self.synthetic_user.email, "password": PASSWORD}
            response = self.browser.post(PREFIX + "login/", data, format="json")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "csrf_failed")
            synthetic_csrf = self.csrf()
            self.assertIn("csrftoken", self.browser.cookies)
            self.assertIn(SYNTHETIC["CSRF_COOKIE_NAME"], self.browser.cookies)
            self.browser.credentials(HTTP_X_CSRFTOKEN=normal_csrf)
            for endpoint in ["login/", "refresh/", "logout/"]:
                with self.subTest(endpoint=endpoint):
                    response = self.browser.post(PREFIX + endpoint, data, format="json")
                    self.assertEqual(response.status_code, 403)
            self.assertFalse(AuthSession.objects.exists())
            self.browser.credentials(HTTP_X_CSRFTOKEN=synthetic_csrf)
            self.login(self.synthetic_user)
            self.assert_signed_in_as(self.synthetic_user)

    def test_cookie_security_attributes_are_preserved_for_both_namespaces(self):
        for namespace in [NORMAL, SYNTHETIC]:
            with self.subTest(namespace=namespace["AUTH_ACCESS_COOKIE_NAME"]):
                with override_settings(**namespace, AUTH_COOKIE_SECURE=True):
                    self.csrf()
                    response = self.login(self.normal_user)
                    for setting, path in [
                        ("AUTH_ACCESS_COOKIE_NAME", "/api/v1/"),
                        ("AUTH_REFRESH_COOKIE_NAME", PREFIX),
                    ]:
                        cookie = response.cookies[namespace[setting]]
                        self.assertTrue(cookie["httponly"])
                        self.assertTrue(cookie["secure"])
                        self.assertEqual(cookie["samesite"], "Lax")
                        self.assertEqual(cookie["path"], path)
