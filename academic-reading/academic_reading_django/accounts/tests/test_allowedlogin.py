from django.test import TestCase

from accounts.models import AllowedLogin


class MatchTests(TestCase):
    def test_exact_email_matches_case_and_space_insensitively(self):
        AllowedLogin.objects.create(identifier="  Abc123@Cam.ac.uk ")
        self.assertEqual(len(AllowedLogin.matches("ABC123@cam.ac.uk")), 1)

    def test_domain_entry_matches_everyone_on_the_domain(self):
        AllowedLogin.objects.create(identifier="@ling.cam.ac.uk")
        self.assertEqual(len(AllowedLogin.matches("x@ling.cam.ac.uk")), 1)
        self.assertEqual(AllowedLogin.matches("x@other.cam.ac.uk"), [])

    def test_crsid_matches_only_cambridge_addresses(self):
        AllowedLogin.objects.create(identifier="abc123")
        self.assertEqual(len(AllowedLogin.matches("abc123@cam.ac.uk")), 1)
        self.assertEqual(AllowedLogin.matches("abc123@evil.example"), [])

    def test_multiple_matching_entries_are_all_returned(self):
        AllowedLogin.objects.create(identifier="abc123@cam.ac.uk")
        AllowedLogin.objects.create(identifier="@cam.ac.uk")
        self.assertEqual(len(AllowedLogin.matches("abc123@cam.ac.uk")), 2)

    def test_no_match_and_blank(self):
        self.assertEqual(AllowedLogin.matches(""), [])
        self.assertEqual(AllowedLogin.matches("nobody@cam.ac.uk"), [])
