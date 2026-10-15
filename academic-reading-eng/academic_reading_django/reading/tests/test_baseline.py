"""Pins today's anonymous behaviour. Must pass unchanged with AUTH_REQUIRED off."""

from django.test import TestCase, override_settings
from django.urls import reverse

from reading.models import ReadingSession


@override_settings(AUTH_REQUIRED=False)
class AnonymousBaselineTests(TestCase):
    def test_home_lists_the_shipped_library(self):
        response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["texts"]), 8)

    def test_open_creates_a_session_and_history_shows_it(self):
        response = self.client.get(reverse("reading:open", kwargs={"source_ref": "marx"}))
        self.assertEqual(response.status_code, 302)
        session = ReadingSession.objects.get()
        self.assertEqual(session.source_ref, "lib:marx")
        self.assertIsNone(session.user)
        history = self.client.get(reverse("reading:history"))
        self.assertContains(history, session.title)
        self.assertContains(history, "this browser")

    def test_health_is_open(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)

    def test_no_sign_out_control_when_anonymous(self):
        self.assertNotContains(self.client.get(reverse("reading:home")), "Sign out")
