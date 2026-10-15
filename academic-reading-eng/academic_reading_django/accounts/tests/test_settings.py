from django.conf import settings
from django.test import SimpleTestCase


class FlagDefaultsTests(SimpleTestCase):
    def test_flags_default_to_dormant(self):
        self.assertFalse(settings.AUTH_REQUIRED)
        self.assertFalse(settings.EMAIL_PASSWORD_LOGIN_ENABLED)

    def test_auth_apps_installed(self):
        for app in ("django.contrib.auth", "django.contrib.admin", "social_django", "accounts", "unfold"):
            self.assertIn(app, settings.INSTALLED_APPS)

    def test_session_cookie_names_unchanged(self):
        self.assertEqual(settings.SESSION_COOKIE_NAME, "are_sessionid")
