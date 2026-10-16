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
        self.assertContains(self._get(), "Sign in with Cambridge (Microsoft)")
        self.assertContains(self._get(), 'class="ms-logo"')

    @override_settings(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="",
    )
    def test_sso_unavailable_message_when_not_configured(self):
        response = self._get()
        self.assertNotContains(response, "Sign in with Cambridge (Microsoft)")
        self.assertContains(response, "Cambridge sign-in is not yet available.")

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
    def test_email_form_shown_only_when_enabled(self):
        self.assertContains(self._get(), 'name="password"')

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=False)
    def test_email_form_hidden_when_disabled(self):
        self.assertNotContains(self._get(), 'name="password"')


class FrontDoorRedirectTests(TestCase):
    """The library page sends anonymous visitors to the sign-in page when a sign-in method exists."""

    SSO = dict(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="id",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="secret",
    )
    NONE = dict(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="",
        EMAIL_PASSWORD_LOGIN_ENABLED=False,
    )

    def test_anonymous_home_redirects_to_login_when_sso_configured(self):
        with override_settings(AUTH_REQUIRED=False, **self.SSO):
            response = self.client.get(reverse("reading:home"))
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)

    def test_anonymous_home_redirects_to_login_when_only_email_login_configured(self):
        with override_settings(AUTH_REQUIRED=False, EMAIL_PASSWORD_LOGIN_ENABLED=True,
                               SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="", SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET=""):
            response = self.client.get(reverse("reading:home"))
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)

    def test_home_stays_open_when_no_sign_in_method_is_configured(self):
        with override_settings(AUTH_REQUIRED=False, **self.NONE):
            self.assertEqual(self.client.get(reverse("reading:home")).status_code, 200)

    def test_signed_in_user_sees_the_library(self):
        from django.contrib.auth.models import User

        self.client.force_login(User.objects.create_user("a@cam.ac.uk", "a@cam.ac.uk"))
        with override_settings(AUTH_REQUIRED=False, **self.SSO):
            self.assertEqual(self.client.get(reverse("reading:home")).status_code, 200)
