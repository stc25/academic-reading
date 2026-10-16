"""What a signed-in reader gets from the library (the bundled texts, all ungrouped)."""

from django.test import TestCase
from django.urls import reverse

from reading.models import LibraryText, ReadingSession
from reading.tests.helpers import prepare_reader


class SignedInBaselineTests(TestCase):
    def setUp(self):
        prepare_reader(self)

    def test_home_lists_the_whole_bundled_library(self):
        response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 200)
        listed = sum(len(pool) for _, pool in response.context["groups"])
        self.assertEqual(listed, 37)
        self.assertEqual(LibraryText.objects.count(), 37)

    def test_open_creates_a_session_and_history_shows_it(self):
        response = self.client.get(reverse("reading:open", kwargs={"source_ref": "de-01"}))
        self.assertEqual(response.status_code, 302)
        session = ReadingSession.objects.get()
        self.assertEqual(session.source_ref, "lib:de-01")
        self.assertEqual(session.user, self.user)
        history = self.client.get(reverse("reading:history"))
        self.assertContains(history, session.title)
        self.assertContains(history, "your account")

    def test_health_is_open_to_everyone(self):
        self.client.logout()
        self.assertEqual(self.client.get("/health/").status_code, 200)

    def test_sign_out_control_is_shown(self):
        self.assertContains(self.client.get(reverse("reading:home")), "Sign out")
