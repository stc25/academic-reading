from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.module_loading import import_string

TENANT = "49a50445-bdfa-4b79-ade3-547b4f3986e9"


class SsoWiringTests(TestCase):
    def test_every_pipeline_step_is_importable(self):
        for dotted in settings.SOCIAL_AUTH_PIPELINE:
            self.assertTrue(callable(import_string(dotted)), dotted)

    def test_allowlist_runs_before_any_user_is_created(self):
        steps = list(settings.SOCIAL_AUTH_PIPELINE)
        self.assertLess(steps.index("accounts.pipeline.enforce_allowlist"),
                        steps.index("social_core.pipeline.user.create_user"))

    @override_settings(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="client-id",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="client-secret",
    )
    def test_begin_redirects_to_the_university_tenant(self):
        response = self.client.post(reverse("social:begin", args=["azuread-tenant-oauth2"]))
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith(f"https://login.microsoftonline.com/{TENANT}/"), location)
        self.assertIn("client_id=client-id", location)
        self.assertIn("/auth/sso/complete/azuread-tenant-oauth2/", location)

    @override_settings(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="client-id",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="client-secret",
    )
    def test_redirect_uri_is_https_behind_the_proxy(self):
        response = self.client.post(
            reverse("social:begin", args=["azuread-tenant-oauth2"]),
            HTTP_X_FORWARDED_PROTO="https", HTTP_HOST="apps.example.org",
        )
        self.assertIn("redirect_uri=https://apps.example.org/auth/sso/complete/", response["Location"])

    @override_settings(
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="client-id",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="client-secret",
    )
    def test_login_page_button_is_a_post_form(self):
        page = self.client.get(reverse("accounts:login"))
        self.assertContains(page, 'method="post" action="%s"' % reverse("social:begin", args=["azuread-tenant-oauth2"]))
