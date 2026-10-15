from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


@override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
class PasswordLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("ext@example.org", "ext@example.org", "s3cret-pass-xyz")

    def _post(self, email, password, **extra):
        return self.client.post(reverse("accounts:login"), {"email": email, "password": password, **extra})

    def test_valid_credentials_log_in_and_redirect_home(self):
        response = self._post("EXT@example.org", "s3cret-pass-xyz")
        self.assertRedirects(response, reverse("reading:home"), fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_password_rejected(self):
        response = self._post("ext@example.org", "nope")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unusable_password_account_cannot_log_in(self):
        invited = User.objects.create_user("inv@example.org", "inv@example.org")
        invited.set_unusable_password()
        invited.save()
        self._post("inv@example.org", "")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_account_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self._post("ext@example.org", "s3cret-pass-xyz")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cambridge_addresses_are_refused_password_login(self):
        User.objects.create_user("abc@cam.ac.uk", "abc@cam.ac.uk", "s3cret-pass-xyz")
        response = self._post("abc@cam.ac.uk", "s3cret-pass-xyz")
        self.assertContains(response, "Cambridge sign-in")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_next_to_other_host_is_ignored(self):
        response = self._post("ext@example.org", "s3cret-pass-xyz", next="https://evil.example/x")
        self.assertRedirects(response, reverse("reading:home"), fetch_redirect_response=False)

    def test_next_same_site_is_followed(self):
        target = reverse("reading:history")
        response = self._post("ext@example.org", "s3cret-pass-xyz", next=target)
        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_throttle_blocks_after_too_many_attempts(self):
        for _ in range(12):
            self._post("ext@example.org", "bad")
        self.assertEqual(self._post("ext@example.org", "s3cret-pass-xyz").status_code, 429)


class FlagOffTests(TestCase):
    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=False)
    def test_password_form_absent_and_post_ignored(self):
        User.objects.create_user("ext@example.org", "ext@example.org", "s3cret-pass-xyz")
        page = self.client.get(reverse("accounts:login"))
        self.assertNotContains(page, 'name="password"')
        self.client.post(reverse("accounts:login"), {"email": "ext@example.org", "password": "s3cret-pass-xyz"})
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="", SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="")
    def test_sso_button_hidden_without_credentials(self):
        self.assertNotContains(self.client.get(reverse("accounts:login")), "Sign in with Cambridge")

    @override_settings(SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="id", SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="s")
    def test_sso_button_shown_with_credentials(self):
        self.assertContains(self.client.get(reverse("accounts:login")), "Sign in with Cambridge")


class LogoutTests(TestCase):
    def test_logout_requires_post_and_clears_session(self):
        user = User.objects.create_user("a@x.org", "a@x.org", "pw-abc-12345")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class SetPasswordTests(TestCase):
    def test_link_sets_password_once_then_expires(self):
        user = User.objects.create_user("n@example.org", "n@example.org")
        user.set_unusable_password()
        user.save()
        url = reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user)})
        page = self.client.get(url, follow=True)
        set_url = page.redirect_chain[-1][0]
        self.client.post(set_url, {"new_password1": "a-Long-pass-9921", "new_password2": "a-Long-pass-9921"})
        user.refresh_from_db()
        self.assertTrue(user.check_password("a-Long-pass-9921"))
        self.assertContains(self.client.get(url), "no longer valid")
