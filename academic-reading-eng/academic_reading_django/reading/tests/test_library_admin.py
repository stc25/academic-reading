from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from reading.models import LibraryText
from reading.tests.helpers import import_library

GERMAN = ("Das ist ein deutscher Text über die Geschichte der Stadt und ihre Bewohner. " * 6)


class LibraryAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root", "root@x.org", "pw-root-12345")
        self.client.force_login(self.admin)
        self.add_url = reverse("admin:reading_librarytext_add")
        self.list_url = reverse("admin:reading_librarytext_changelist")

    def post_new(self, **extra):
        data = {"source_ref": "new-1", "title": "New", "language": "German", "body": GERMAN, "active": "on", "groups": []}
        data.update(extra)
        return self.client.post(self.add_url, data)

    def test_add_a_text_by_pasting_and_ticking_a_group(self):
        group = Group.objects.create(name="Arabic")
        response = self.post_new(groups=[group.pk])
        self.assertEqual(response.status_code, 302)
        text = LibraryText.objects.get(source_ref="new-1")
        self.assertEqual(list(text.groups.all()), [group])

    def test_upload_a_file_fills_in_the_body_and_detects_the_language(self):
        response = self.client.post(self.add_url, {
            "source_ref": "up-1", "title": "", "language": "", "body": "", "active": "on",
            "file": SimpleUploadedFile("Stadt.txt", GERMAN.encode()),
        })
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        text = LibraryText.objects.get(source_ref="up-1")
        self.assertEqual(text.lang, "de")
        self.assertEqual(text.language_name, "German")
        self.assertEqual(text.title, "Stadt")
        self.assertTrue(text.body.startswith("Das ist ein deutscher Text"))

    def test_empty_body_and_no_file_is_refused(self):
        response = self.post_new(body="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LibraryText.objects.exists())

    def _action(self, name, refs, **extra):
        pks = list(LibraryText.objects.filter(source_ref__in=refs).values_list("pk", flat=True))
        return self.client.post(self.list_url, {"action": name, "_selected_action": pks, **extra})

    def test_bulk_add_to_group_asks_for_the_group_then_changes_only_the_selected_texts(self):
        import_library()
        group = Group.objects.create(name="German")
        refs = list(LibraryText.objects.filter(lang="de").values_list("source_ref", flat=True))
        page = self._action("add_to_group", refs)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "German")
        self.assertEqual(group.library_texts.count(), 0)
        done = self._action("add_to_group", refs, apply="1", group=group.pk)
        self.assertEqual(done.status_code, 302)
        self.assertEqual(set(group.library_texts.values_list("source_ref", flat=True)), set(refs))
        self.assertEqual(group.library_texts.count(), len(refs))
        self.assertEqual(LibraryText.objects.filter(groups__isnull=True).count(), 8 - len(refs))

    def test_bulk_remove_from_group(self):
        import_library()
        group = Group.objects.create(name="Everyone")
        everything = list(LibraryText.objects.values_list("source_ref", flat=True))
        self._action("add_to_group", everything, apply="1", group=group.pk)
        self._action("remove_from_group", ["marx"], apply="1", group=group.pk)
        self.assertEqual(group.library_texts.count(), 7)

    def test_bulk_activate_and_deactivate(self):
        import_library()
        self._action("deactivate", ["marx", "andrade"])
        self.assertEqual(LibraryText.objects.filter(active=False).count(), 2)
        self._action("activate", ["marx"])
        self.assertEqual(LibraryText.objects.filter(active=False).count(), 1)

    def test_changelist_filters_by_group_and_language(self):
        import_library()
        group = Group.objects.create(name="G")
        LibraryText.objects.get(source_ref="marx").groups.add(group)
        page = self.client.get(self.list_url, {"groups__id__exact": group.pk})
        self.assertContains(page, "marx")
        self.assertNotContains(page, "andrade")
