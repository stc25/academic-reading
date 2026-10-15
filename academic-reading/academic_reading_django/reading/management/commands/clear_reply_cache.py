from django.core.management.base import BaseCommand, CommandError

from reading.models import CachedReply


class Command(BaseCommand):
    help = (
        "Delete cached LLM opening replies so they are regenerated on next use. "
        "Entries are keyed on the exact prompt, so editing a text, prompts.yaml "
        "or config.yaml already bypasses stale ones; use this to force a refresh "
        "anyway (e.g. after the model itself is upgraded) or to drop a bad reply."
    )

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Delete every cached reply.")
        parser.add_argument("--activity", help="Only this activity id, e.g. structure.")
        parser.add_argument("--text", help="Only this library text id, e.g. de-01 (stored as lib:de-01).")

    def handle(self, *args, all=False, activity=None, text=None, **options):
        if not (all or activity or text):
            raise CommandError("Say what to clear: --all, --activity ID and/or --text ID.")
        rows = CachedReply.objects.all()
        if activity:
            rows = rows.filter(activity_id=activity)
        if text:
            rows = rows.filter(source_ref=text if text.startswith("lib:") else f"lib:{text}")
        deleted, _ = rows.delete()
        self.stdout.write(f"deleted={deleted}")
