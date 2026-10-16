from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth.models import Group
from django.test import TestCase

from reading.models import LibraryText


def run(*args):
    out = StringIO()
    call_command("import_library", *args, stdout=out)
    return out.getvalue()


class ImportLibraryTests(TestCase):
    def test_imports_the_bundled_library(self):
        run()
        self.assertEqual(LibraryText.objects.count(), 37)
        by_lang = {}
        for row in LibraryText.objects.all():
            by_lang[row.lang] = by_lang.get(row.lang, 0) + 1
        self.assertEqual(by_lang, {"de": 11, "fr": 8, "it": 10, "zh": 8})

    def test_keeps_source_refs_so_history_links_still_work(self):
        run()
        self.assertTrue(LibraryText.objects.filter(source_ref="de-01").exists())

    def test_rerun_is_idempotent_and_never_overwrites_admin_changes(self):
        run()
        group = Group.objects.create(name="G")
        row = LibraryText.objects.get(source_ref="de-01")
        row.groups.add(group)
        row.active = False
        row.title = "Edited in the admin"
        row.save()
        run()
        row.refresh_from_db()
        self.assertEqual(LibraryText.objects.count(), 37)
        self.assertEqual(row.title, "Edited in the admin")
        self.assertEqual(list(row.groups.all()), [group])
        self.assertFalse(row.active)

    def test_update_refreshes_content_but_keeps_groups_and_active(self):
        run()
        group = Group.objects.create(name="G")
        row = LibraryText.objects.get(source_ref="de-01")
        original_title = row.title
        row.groups.add(group)
        row.active = False
        row.title = "Edited"
        row.save()
        run("--update")
        row.refresh_from_db()
        self.assertEqual(row.title, original_title)
        self.assertEqual(list(row.groups.all()), [group])
        self.assertFalse(row.active)

    def test_if_empty_does_nothing_once_there_are_texts(self):
        run()
        LibraryText.objects.filter(source_ref="de-01").delete()
        self.assertIn("nothing to do", run("--if-empty"))
        self.assertEqual(LibraryText.objects.count(), 36)

    def test_check_passes_after_import_and_fails_on_a_difference(self):
        run()
        self.assertIn("check passed", run("--check"))
        LibraryText.objects.filter(source_ref="de-01").update(body="tampered")
        with self.assertRaises(CommandError) as ctx:
            run("--check")
        self.assertIn("de-01: body differs", str(ctx.exception))

    def test_check_fails_when_a_text_is_missing(self):
        run()
        LibraryText.objects.filter(source_ref="de-02").delete()
        with self.assertRaises(CommandError):
            run("--check")
