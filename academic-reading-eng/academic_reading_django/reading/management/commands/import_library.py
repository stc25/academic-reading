"""Load the bundled library (sources/ + source.cfg) into LibraryText.

Default: create texts that are missing and leave existing rows untouched (so admin edits, groups and
"active" survive restarts). ``--if-empty`` does nothing unless the table is empty (used by the container
entrypoint). ``--update`` also refreshes the content fields of existing rows, never ``groups`` or ``active``.
``--check`` compares the database with the files and fails on any difference.
"""

from django.core.management.base import BaseCommand, CommandError

from reading.logic.corpus import load_library
from reading.logic.settings import load_config
from reading.models import LibraryText


def _values(text) -> dict:
    return {
        "title": text.title,
        "author": text.author,
        "language": text.language_name,
        "level": text.level_value,
        "source": text.source,
        "notes": text.notes,
        "body": text.body,
    }


# Worked out by LibraryText.save(); compared by --check as well.
DERIVED = (("lang", "lang"), ("language_name", "language_name"), ("script", "script"))


class Command(BaseCommand):
    help = "Import the bundled library into the database (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--if-empty", action="store_true", help="Do nothing unless there are no library texts yet.")
        parser.add_argument("--update", action="store_true", help="Refresh content fields of existing texts.")
        parser.add_argument("--check", action="store_true", help="Compare the database with the files; exit non-zero on any difference.")

    def handle(self, *args, **opts):
        texts, problems = load_library(load_config())
        for problem in problems:
            self.stderr.write(f"warning: {problem}")
        if opts["check"]:
            return self._check(texts)
        if opts["if_empty"] and LibraryText.objects.exists():
            self.stdout.write("Library already imported; nothing to do.")
            return

        created = updated = skipped = 0
        for text in texts:
            row = LibraryText.objects.filter(source_ref=text.id).first()
            if row is None:
                LibraryText.objects.create(source_ref=text.id, **_values(text))
                created += 1
            elif opts["update"]:
                for field, value in _values(text).items():
                    setattr(row, field, value)
                row.save()
                updated += 1
            else:
                skipped += 1
        self.stdout.write(f"Imported {created} new, {updated} updated, {skipped} left as they were ({len(texts)} in files).")

    def _check(self, texts):
        problems = []
        rows = {r.source_ref: r for r in LibraryText.objects.all()}
        for text in texts:
            row = rows.pop(text.id, None)
            if row is None:
                problems.append(f"missing in database: {text.id}")
                continue
            for field, value in _values(text).items():
                if getattr(row, field) != value:
                    problems.append(f"{text.id}: {field} differs")
            for row_field, text_field in DERIVED:
                if getattr(row, row_field) != getattr(text, text_field):
                    problems.append(f"{text.id}: {row_field} differs")
        for extra in rows:
            self.stdout.write(f"note: {extra} is in the database but not in the files (added in the admin?)")
        if problems:
            raise CommandError("Library check failed:\n  " + "\n  ".join(problems))
        self.stdout.write(self.style.SUCCESS(f"Library check passed: {len(texts)} texts match."))
