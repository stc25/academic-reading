from django.conf import settings
from django.test import SimpleTestCase


class FlagDefaultsTests(SimpleTestCase):
    def test_email_login_defaults_off_and_sign_in_is_not_a_switch(self):
        self.assertFalse(settings.EMAIL_PASSWORD_LOGIN_ENABLED)
        self.assertFalse(hasattr(settings, "AUTH_REQUIRED"))

    def test_library_comes_from_the_database_by_default(self):
        self.assertEqual(settings.LIBRARY_SOURCE, "db")

    def test_auth_apps_installed(self):
        for app in ("django.contrib.auth", "django.contrib.admin", "social_django", "accounts", "unfold"):
            self.assertIn(app, settings.INSTALLED_APPS)

    def test_session_cookie_names_unchanged(self):
        self.assertEqual(settings.SESSION_COOKIE_NAME, "are_sessionid")
