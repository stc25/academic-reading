from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AllowedLogin
from accounts.services import send_account_created_email


class EmailServiceTests(TestCase):
    def test_email_has_set_password_link_and_no_password(self):
        user = User.objects.create_user("n@example.org", "n@example.org", first_name="Ann <b>")
        send_account_created_email(user)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["n@example.org"])
        self.assertIn("/auth/password-set/", message.body)
        html = message.alternatives[0][0]
        self.assertNotIn("<b>", html)


class AdminCreateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root", "root@x.org", "pw-root-12345")
        self.client.force_login(self.admin)

    def _add(self):
        return self.client.post(reverse("admin:auth_user_add"), {
            "email": "New@Example.org", "first_name": "N", "last_name": "U"})

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
    def test_creating_user_makes_passwordless_account_and_sends_one_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            self._add()
        user = User.objects.get(username="new@example.org")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.email, "new@example.org")
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=False)
    def test_no_email_while_the_feature_is_dormant(self):
        with self.captureOnCommitCallbacks(execute=True):
            self._add()
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
    def test_sso_style_user_creation_outside_admin_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            User.objects.create_user("sso@cam.ac.uk", "sso@cam.ac.uk")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
    def test_resend_action(self):
        user = User.objects.create_user("r@example.org", "r@example.org")
        self.client.post(reverse("admin:auth_user_changelist"),
                         {"action": "resend_set_password_email", "_selected_action": [user.pk]})
        self.assertEqual(len(mail.outbox), 1)

    def test_allowedlogin_changelist_and_add_load(self):
        AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        self.assertEqual(self.client.get(reverse("admin:accounts_allowedlogin_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:accounts_allowedlogin_add")).status_code, 200)
