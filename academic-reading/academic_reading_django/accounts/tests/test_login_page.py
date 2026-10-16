from django.test import TestCase, override_settings
from django.urls import reverse


class LoginLandingPageTests(TestCase):
    def _get(self):
        return self.client.get(reverse("accounts:login"))

    def test_renders_brand_panel_and_card(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="auth-panel"')
        self.assertContains(response, 'class="auth-card"')
        self.assertContains(response, "reading/css/login.css")

    @override_settings(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="id",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="secret",
    )
    def test_sso_button_shown_when_configured(self):
        response = self._get()
        self.assertContains(response, "Sign in with Cambridge")
        self.assertContains(response, "University account")
        self.assertContains(self._get(), 'class="ms-logo"')

    @override_settings(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="",
    )
    def test_sso_unavailable_message_when_not_configured(self):
        response = self._get()
        self.assertNotContains(response, "Sign in with Cambridge")
        self.assertContains(response, "Cambridge sign-in is not yet available.")

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
    def test_email_form_shown_only_when_enabled(self):
        self.assertContains(self._get(), 'name="password"')

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=False)
    def test_email_form_hidden_when_disabled(self):
        self.assertNotContains(self._get(), 'name="password"')


class SignInGateTests(TestCase):
    """Sign-in is mandatory: signed-out visitors are sent to the sign-in page."""

    SSO = dict(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="id",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="secret",
    )

    def test_anonymous_home_redirects_to_login_when_sso_configured(self):
        with override_settings(**self.SSO):
            response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("accounts:login")))

    def test_anonymous_home_redirects_to_login_when_only_email_login_configured(self):
        with override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True,
                               SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="", SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET=""):
            response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 302)

    def test_signed_in_user_gets_the_library_page(self):
        from django.contrib.auth.models import User

        self.client.force_login(User.objects.create_user("a@cam.ac.uk", "a@cam.ac.uk"))
        with override_settings(**self.SSO):
            self.assertEqual(self.client.get(reverse("reading:home")).status_code, 200)
