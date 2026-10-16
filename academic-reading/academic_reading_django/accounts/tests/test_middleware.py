from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(AUTH_REQUIRED=True)
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


@override_settings(AUTH_REQUIRED=False, SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="", SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="", EMAIL_PASSWORD_LOGIN_ENABLED=False)
class DormantGateTests(TestCase):
    def test_anonymous_passes_when_switch_is_off(self):
        self.assertEqual(self.client.get(reverse("reading:home")).status_code, 200)
