"""What a signed-in reader gets from the library (the shipped texts, all ungrouped)."""

from django.test import TestCase
from django.urls import reverse

from reading.models import LibraryText, ReadingSession
from reading.tests.helpers import prepare_reader


class SignedInBaselineTests(TestCase):
    def setUp(self):
        prepare_reader(self)

    def test_home_lists_the_shipped_library(self):
        response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["texts"]), 8)
        self.assertEqual(LibraryText.objects.count(), 8)

    def test_open_creates_a_session_and_history_shows_it(self):
        response = self.client.get(reverse("reading:open", kwargs={"source_ref": "marx"}))
        self.assertEqual(response.status_code, 302)
        session = ReadingSession.objects.get()
        self.assertEqual(session.source_ref, "lib:marx")
        self.assertEqual(session.user, self.user)
        history = self.client.get(reverse("reading:history"))
        self.assertContains(history, session.title)
        self.assertContains(history, "your account")

    def test_health_is_open_to_everyone(self):
        self.client.logout()
        self.assertEqual(self.client.get("/health/").status_code, 200)

    def test_sign_out_control_is_shown(self):
        self.assertContains(self.client.get(reverse("reading:home")), "Sign out")
