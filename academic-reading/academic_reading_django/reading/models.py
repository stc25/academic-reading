"""Session-scoped reading history — no accounts, so `session_key` is the only
identity a row has. `ActivityTurn` is append-only: every Generate/Regenerate/
Submit click inserts a new row, and that log *is* the history feature.

Unlike academic-reading-eng, proficiency level and reply-language are not
properties of the text — the reader chooses them per generation, so they
live on `ActivityTurn` rather than `ReadingSession`.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .logic.corpus import LANG_NAMES, Text


class ReadingSession(models.Model):
    """One text a browser has opened — library or uploaded, body included.

    The body is stored even for library texts (not just uploads) so a
    browser's history stays self-contained and readable even if the bundled
    manifest changes later.
    """

    session_key = models.CharField(max_length=40, db_index=True)
    # Always set for new rows (sign-in is mandatory); old anonymous rows keep user=None.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reading_sessions",
    )
    source_ref = models.CharField(max_length=300)
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=300, blank=True)
    year = models.CharField(max_length=10, blank=True)
    topic = models.CharField(max_length=200, blank=True)
    copyright = models.CharField(max_length=100, blank=True)
    excerpt = models.CharField(max_length=500, blank=True)
    source = models.CharField(max_length=500, blank=True)
    lang = models.CharField(max_length=10)
    script = models.CharField(max_length=20, blank=True)
    register = models.CharField(max_length=50, blank=True)
    body = models.TextField()
    uploaded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def language_name(self) -> str:
        return LANG_NAMES.get(self.lang, self.lang)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session_key", "source_ref"], name="unique_session_source_ref"
            ),
            models.UniqueConstraint(
                fields=["user", "source_ref"],
                condition=models.Q(user__isnull=False),
                name="unique_user_source_ref",
            ),
        ]
        indexes = [models.Index(fields=["session_key", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.title} ({self.source_ref})"


class ActivityTurn(models.Model):
    """One model call (or the reader's draft ahead of one)."""

    OPENING = "user"
    FEEDBACK = "feedback"
    TURN_CHOICES = [(OPENING, "Opening"), (FEEDBACK, "Feedback")]

    session = models.ForeignKey(ReadingSession, on_delete=models.CASCADE, related_name="turns")
    activity_id = models.CharField(max_length=50)
    turn = models.CharField(max_length=10, choices=TURN_CHOICES)
    level_id = models.CharField(max_length=30)
    reply_language = models.CharField(max_length=50)
    model = models.CharField(max_length=100, blank=True)
    draft = models.TextField(blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["session", "activity_id", "-created_at"])]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.activity_id}/{self.turn} @ {self.created_at:%Y-%m-%d %H:%M}"


class CachedReply(models.Model):
    """A shared, reader-independent copy of one *opening* turn.

    Opening replies depend only on the text, activity, level, reply language,
    model, sampling options and prompts, so the first reader's reply is served
    to everyone after them instead of calling the LLM again (see
    docs/experiments/reply-variance: repeat runs differ in wording but not in
    structure, length or substance). ``key`` is a SHA-256 of everything that
    went into the call — the exact system and user messages (which embed the
    text body, level, language, metadata and prompts), the model and the
    options — so editing a text, prompts.yaml or config.yaml misses the cache
    automatically. Uploaded texts and feedback turns are never stored here.
    The other columns are for inspection and selective clearing only.
    """

    key = models.CharField(max_length=64, unique=True)
    activity_id = models.CharField(max_length=50)
    level_id = models.CharField(max_length=30)
    reply_language = models.CharField(max_length=50)
    model = models.CharField(max_length=100)
    source_ref = models.CharField(max_length=300, blank=True)
    content = models.TextField()
    hits = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["activity_id", "source_ref"])]

    def __str__(self) -> str:
        return f"{self.source_ref}/{self.activity_id}/{self.level_id}/{self.reply_language}"

    @staticmethod
    def make_key(model: str, system: str, user: str, options: dict | None) -> str:
        import hashlib
        import json

        payload = json.dumps(
            [model, system, user, options or {}], sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def store(cls, *, key, activity_id, level_id, reply_language, model, source_ref, content) -> None:
        """Insert unless another request already stored this key (first wins)."""
        from django.db import IntegrityError, transaction

        try:
            with transaction.atomic():
                cls.objects.get_or_create(
                    key=key,
                    defaults=dict(
                        activity_id=activity_id, level_id=level_id, reply_language=reply_language,
                        model=model, source_ref=source_ref, content=content,
                    ),
                )
        except IntegrityError:
            pass


class LibraryText(models.Model):
    """One text in the library, managed in the admin.

    ``groups`` limits who may read it: no groups = every signed-in reader; otherwise only members of
    at least one of those groups (plus staff and groups marked "sees every text"). See ``reading.access``.
    """

    source_ref = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Short permanent id, e.g. de-01. Reading history links to it, so do not change it once readers have used the text.",
    )
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=300, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    lang = models.CharField("language", max_length=10, choices=list(LANG_NAMES.items()))
    topic = models.CharField(max_length=200, blank=True)
    register = models.CharField(max_length=50, blank=True)
    copyright = models.CharField(max_length=100, blank=True)
    excerpt = models.CharField(max_length=500, blank=True)
    source = models.CharField(max_length=500, blank=True)
    script = models.CharField(max_length=20, blank=True)
    body = models.TextField()
    active = models.BooleanField(default=True, help_text="Untick to hide the text from readers without deleting it.")
    groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="library_texts",
        help_text="Leave empty to make the text available to every signed-in reader.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["lang", "source_ref"]

    def __str__(self) -> str:
        return f"{self.source_ref}: {self.title}"

    def to_text(self) -> Text:
        return Text(
            id=self.source_ref,
            lang=self.lang,
            title=self.title,
            body=self.body,
            author=self.author,
            year=self.year,
            topic=self.topic,
            copyright=self.copyright,
            excerpt=self.excerpt,
            source=self.source,
            script=self.script,
            register=self.register,
        )
