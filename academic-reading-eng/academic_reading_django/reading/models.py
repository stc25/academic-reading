"""Session-scoped reading history — no accounts, so `session_key` is the only
identity a row has. `ActivityTurn` is append-only: every Generate/Regenerate/
Submit click inserts a new row, and that log *is* the history feature.
"""

from __future__ import annotations

from django.db import models


class ReadingSession(models.Model):
    """One text a browser has opened — library or uploaded, body included.

    The body is stored even for library texts (not just uploads) so a
    browser's history stays self-contained and readable even if sources/ or
    source.cfg changes later.
    """

    session_key = models.CharField(max_length=40, db_index=True)
    source_ref = models.CharField(max_length=300)
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=300, blank=True)
    language_code = models.CharField(max_length=20, blank=True)
    language_name = models.CharField(max_length=100, blank=True)
    level_id = models.CharField(max_length=30)
    script = models.CharField(max_length=20, blank=True)
    body = models.TextField()
    source = models.CharField(max_length=500, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    uploaded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session_key", "source_ref"], name="unique_session_source_ref"
            )
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

    Opening replies depend only on the text, activity, the text's level,
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
    reply_language = models.CharField(max_length=50, blank=True)  # always English here
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
