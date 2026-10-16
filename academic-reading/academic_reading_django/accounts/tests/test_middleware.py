from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
class AuthGateTests(TestCase):
    def test_anonymous_is_redirected_to_login_with_next(self):
        response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("accounts:login")))
        self.assertIn("next=", response["Location"])

    def test_every_reading_route_is_gated(self):
        for name, kwargs in (
            ("reading:history", {}),
            ("reading:open", {"source_ref": "de-01"}),
            ("reading:read", {"pk": 1}),
        ):
            response = self.client.get(reverse(name, kwargs=kwargs))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("/auth/login/", response["Location"], name)

    def test_exempt_paths_stay_open(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)

    def test_signed_in_user_passes(self):
        user = User.objects.create_user("a@cam.ac.uk", "a@cam.ac.uk")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("reading:home")).status_code, 200)


@override_settings(
    SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="", SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="",
    EMAIL_PASSWORD_LOGIN_ENABLED=False,
)
class NoSignInMethodTests(TestCase):
    def test_anonymous_gets_a_clear_503_instead_of_a_dead_end_login(self):
        response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Sign-in is not set up", status_code=503)

    def test_health_and_login_page_still_open(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
