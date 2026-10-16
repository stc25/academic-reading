"""Who may read which library text. The one place the rule lives.

1. Not signed in -> nothing.
2. Staff / superusers, and members of a group marked "sees every text" -> every active text.
3. Everyone else -> active texts with no groups, plus active texts limited to one of their groups.

Evaluated on every request, so a group change takes effect on the person's next page load.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q

from .logic.corpus import Text, load_library
from .models import LibraryText, ReadingSession


def sees_every_text(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    return user.groups.filter(access__sees_all_texts=True).exists()


def texts_visible_to(user):
    """Queryset of LibraryText rows this person may read."""
    active = LibraryText.objects.filter(active=True)
    if not user.is_authenticated:
        return active.none()
    if sees_every_text(user):
        return active
    return active.filter(Q(groups__isnull=True) | Q(groups__in=user.groups.all())).distinct()


def library_for(user) -> list[Text]:
    """The Text objects this person may read (ungrouped everything in ``files`` mode)."""
    if not user.is_authenticated:
        return []
    if settings.LIBRARY_SOURCE == "files":
        return load_library()[1]
    return [t.to_text() for t in texts_visible_to(user)]


def can_open(user, session: ReadingSession) -> bool:
    """Library sessions need the text to still be visible; uploads and old rows are the owner's own."""
    if session.uploaded or not session.source_ref.startswith("lib:"):
        return True
    if settings.LIBRARY_SOURCE == "files":
        return True
    ref = session.source_ref.removeprefix("lib:")
    return texts_visible_to(user).filter(source_ref=ref).exists()


def visible_sessions(user, sessions):
    """Drop sessions for library texts the person can no longer see."""
    sessions = list(sessions)
    if settings.LIBRARY_SOURCE == "files":
        return sessions
    visible = set(texts_visible_to(user).values_list("source_ref", flat=True))
    return [
        s for s in sessions
        if s.uploaded or not s.source_ref.startswith("lib:") or s.source_ref.removeprefix("lib:") in visible
    ]
