from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from accounts import pipeline
from accounts.models import AllowedLogin
from accounts.pipeline import AuthForbidden


class EnforceAllowlistTests(TestCase):
    def test_rejects_unlisted_email_and_creates_nothing(self):
        with self.assertRaises(pipeline.NotAllowlisted):
            pipeline.enforce_allowlist(None, {"email": "stranger@cam.ac.uk"}, object())
        self.assertEqual(User.objects.count(), 0)

    def test_notallowlisted_is_an_authforbidden_with_helpful_message(self):
        exc = pipeline.NotAllowlisted(object())
        self.assertIsInstance(exc, AuthForbidden)
        self.assertIn("allowed list", str(exc))

    def test_rejects_missing_email(self):
        with self.assertRaises(pipeline.NotAllowlisted):
            pipeline.enforce_allowlist(None, {}, object())

    def test_accepts_listed_email_returning_entry_pks(self):
        entry = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        out = pipeline.enforce_allowlist(None, {"email": "A@cam.ac.uk"}, object())
        self.assertEqual(out["allowed_entries"], [entry.pk])


class FinishLoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@cam.ac.uk", "")

    def _run(self, user, entries):
        pipeline.finish_login(None, {"email": "a@cam.ac.uk"}, object(), user=user,
                              allowed_entries=[e.pk for e in entries])

    def test_fills_in_a_missing_email(self):
        e1 = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        self._run(self.user, [e1])
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "a@cam.ac.uk")

    def test_links_matched_user_to_the_specific_entry_not_the_domain_one(self):
        specific = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        domain = AllowedLogin.objects.create(identifier="@cam.ac.uk")
        self._run(self.user, [specific, domain])
        specific.refresh_from_db(); domain.refresh_from_db()
        self.assertEqual(specific.matched_user, self.user)
        self.assertIsNone(domain.matched_user)

    def test_inactive_user_is_refused(self):
        self.user.is_active = False
        self.user.save()
        e1 = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        with self.assertRaises(AuthForbidden):
            self._run(self.user, [e1])

    def test_reports_the_login_as_sso(self):
        e1 = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        with mock.patch("accounts.pipeline.report_login") as report:
            self._run(self.user, [e1])
        report.assert_called_once_with("a@cam.ac.uk", "sso")

    def test_no_user_is_a_noop(self):
        self.assertIsNone(pipeline.finish_login(None, {}, object(), user=None))
