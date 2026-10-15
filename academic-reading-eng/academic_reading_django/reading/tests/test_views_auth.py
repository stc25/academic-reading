from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from reading.models import ReadingSession


@override_settings(AUTH_REQUIRED=True)
class OwnerScopedHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@x.org", "a@x.org")
        self.client.force_login(self.user)

    def _open(self, ref="marx"):
        return self.client.get(reverse("reading:open", kwargs={"source_ref": ref}))

    def test_session_belongs_to_the_user(self):
        self._open()
        self.assertEqual(ReadingSession.objects.get().user, self.user)

    def test_reopening_reuses_the_users_session_across_logins(self):
        self._open()
        self.client.post(reverse("accounts:logout"))
        self.client.force_login(self.user)
        self._open()
        self.assertEqual(ReadingSession.objects.count(), 1)

    def test_other_users_cannot_read_my_session_or_history(self):
        self._open()
        mine = ReadingSession.objects.get()
        other = User.objects.create_user("b@x.org", "b@x.org")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("reading:read", kwargs={"pk": mine.pk})).status_code, 404)
        self.assertNotContains(self.client.get(reverse("reading:history")), mine.title)
        self.assertEqual(self.client.get(reverse("reading:home")).context["history"], [])

    def test_uploads_are_private_to_the_uploader(self):
        self.client.post(reverse("reading:upload"), {
            "file": SimpleUploadedFile("mine.txt", ("Das ist mein eigener deutscher Text. " * 10).encode()),
            "language": "de"})
        self.assertEqual(ReadingSession.objects.get().user, self.user)
        self.client.force_login(User.objects.create_user("b@x.org", "b@x.org"))
        self.assertNotContains(self.client.get(reverse("reading:history")), "mine")

    def test_history_copy_mentions_account(self):
        page = self.client.get(reverse("reading:history"))
        self.assertContains(page, "your account")
        self.assertNotContains(page, "this browser")

    def test_sign_out_control_shown_when_signed_in(self):
        self.assertContains(self.client.get(reverse("reading:home")), "Sign out")

    def test_anonymous_rows_stay_unreachable_when_auth_is_on(self):
        old = ReadingSession.objects.create(
            session_key="legacykey", source_ref="lib:marx", title="Legacy", language_code="de", language_name="German", level_id="intermediate", body="x"
        )
        self.assertEqual(self.client.get(reverse("reading:read", kwargs={"pk": old.pk})).status_code, 404)
