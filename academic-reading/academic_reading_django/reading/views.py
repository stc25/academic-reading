"""Views for the reading app.

Server-rendered. History is session-scoped (anonymous) or per-user (AUTH_REQUIRED). Unlike academic-reading-eng,
proficiency level and reply-language are reader choices carried in the query
string (?level=...&reply=...) rather than fixed per text, so every link,
button and form on the activity page threads them through explicitly.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponseBadRequest, StreamingHttpResponse
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .logic.annotate import body_html, locate_notes, notes_markdown, parse_notes
from .logic.corpus import LANG_NAMES, Text, load_library, text_from_upload
from .logic.llm import LLMError, stream_reply
from .logic.prompts import available_templates, build_brief, build_messages, load_prompts
from .logic.settings import Activity, Config, load_config
from .markdown_utils import render_markdown
from .models import ActivityTurn, CachedReply, ReadingSession


def _config() -> Config:
    return load_config()


def _session_key(request) -> str:
    return request.session.session_key or ""


def _ensure_session_key(request) -> str:
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _owner(request) -> dict:
    """The ReadingSession filter identifying whose history this is."""
    if settings.AUTH_REQUIRED:
        return {"user": request.user}
    return {"session_key": _session_key(request)}


def _owner_lookup(request) -> tuple[dict, dict]:
    """(get_or_create lookup, extra defaults) for creating a ReadingSession."""
    key = _ensure_session_key(request)
    if settings.AUTH_REQUIRED:
        return {"user": request.user}, {"session_key": key}
    return {"session_key": key}, {}


def _get_session(request, pk: int) -> ReadingSession:
    return get_object_or_404(ReadingSession, pk=pk, **_owner(request))


def _get_activity(activity_id: str, config: Config) -> Activity:
    for activity in config.activities:
        if activity.id == activity_id:
            return activity
    raise Http404("Unknown activity.")


def _session_to_text(session: ReadingSession) -> Text:
    return Text(
        id=session.source_ref,
        lang=session.lang,
        title=session.title,
        body=session.body,
        author=session.author,
        year=int(session.year) if session.year else None,
        topic=session.topic,
        copyright=session.copyright,
        excerpt=session.excerpt,
        source=session.source,
        script=session.script,
        register=session.register,
        uploaded=session.uploaded,
    )


def _resolved_level(request, config: Config):
    level_id = request.GET.get("level") or config.default_level.id
    return config.level(level_id)


def _reply_choices(activity: Activity, text: Text) -> tuple[str, str]:
    return "English", text.language_name


def _resolved_reply(request, activity: Activity, text: Text) -> str:
    choices = _reply_choices(activity, text)
    default = choices[0 if activity.response_language == "en" else 1]
    reply = request.GET.get("reply") or default
    return reply if reply in choices else default


def _query(level_id: str, reply_language: str) -> str:
    from urllib.parse import urlencode

    return urlencode({"level": level_id, "reply": reply_language})


# --------------------------------------------------------------------------- #
# Library / upload
# --------------------------------------------------------------------------- #
def home_view(request):
    _, texts = load_library()

    groups = []
    for code, name in LANG_NAMES.items():
        pool = sorted((t for t in texts if t.lang == code), key=lambda t: t.id)
        if pool:
            groups.append((name, pool))

    history = []
    if settings.AUTH_REQUIRED or _session_key(request):
        history = list(ReadingSession.objects.filter(**_owner(request)).order_by("-created_at"))

    return render(
        request,
        "reading/home.html",
        {"groups": groups, "history": history, "lang_names": LANG_NAMES},
    )


def open_view(request, source_ref: str):
    _, texts = load_library()
    text = next((t for t in texts if t.id == source_ref), None)
    if text is None:
        raise Http404("Text not found.")

    lookup, extra = _owner_lookup(request)
    session, _created = ReadingSession.objects.get_or_create(
        source_ref=f"lib:{text.id}",
        **lookup,
        defaults=dict(
            **extra,
            title=text.title,
            author=text.author,
            year=str(text.year) if text.year else "",
            topic=text.topic,
            copyright=text.copyright,
            excerpt=text.excerpt,
            source=text.source,
            lang=text.lang,
            script=text.script,
            register=text.register,
            body=text.body,
            uploaded=False,
        ),
    )
    config = _config()
    return redirect("reading:activity", pk=session.pk, activity_id=config.activities[0].id)


@require_POST
def upload_view(request):
    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Choose a file to upload.")
        return redirect("reading:home")

    text = text_from_upload(upload.name, upload.read())

    chosen_lang = (request.POST.get("language") or "").strip()
    if chosen_lang in LANG_NAMES:
        text.lang = chosen_lang
    if not text.lang:
        messages.error(
            request,
            "Could not detect the language of that file — choose German, "
            "French, Italian or Chinese and upload it again.",
        )
        return redirect("reading:home")

    lookup, extra = _owner_lookup(request)
    source_ref = "upload:" + hashlib.sha1(text.body.encode("utf-8")).hexdigest()[:16]
    session, _created = ReadingSession.objects.get_or_create(
        source_ref=source_ref,
        **lookup,
        defaults=dict(
            **extra,
            title=text.title,
            author="",
            year="",
            topic="",
            copyright="",
            excerpt="",
            source="",
            lang=text.lang,
            script=text.script,
            register="",
            body=text.body,
            uploaded=True,
        ),
    )
    config = _config()
    return redirect("reading:activity", pk=session.pk, activity_id=config.activities[0].id)


@require_POST
def reset_view(request, pk: int):
    """Delete everything generated for this text — the reader starts over.

    Deleting the ReadingSession cascades to every ActivityTurn for it. A
    library text is immediately reopened as a fresh session; an upload has
    nowhere to reopen to (its body only ever lived in this row), so it just
    goes back to the library.
    """
    session = _get_session(request, pk)
    source_ref = session.source_ref
    uploaded = session.uploaded
    session.delete()
    messages.success(request, "Reset — everything generated for this text has been removed.")
    if uploaded:
        return redirect("reading:home")
    return redirect("reading:open", source_ref=source_ref.removeprefix("lib:"))


# --------------------------------------------------------------------------- #
# Reading + activities
# --------------------------------------------------------------------------- #
def read_redirect_view(request, pk: int):
    session = _get_session(request, pk)
    config = _config()
    return redirect("reading:activity", pk=session.pk, activity_id=config.activities[0].id)


@ensure_csrf_cookie
def activity_view(request, pk: int, activity_id: str):
    session = _get_session(request, pk)
    config = _config()
    prompts = load_prompts()
    activity = _get_activity(activity_id, config)
    level = _resolved_level(request, config)
    text = _session_to_text(session)
    reply_language = _resolved_reply(request, activity, text)
    turns = available_templates(activity.id, prompts)

    common = dict(session=session, activity_id=activity.id, level_id=level.id, reply_language=reply_language)

    opening = None
    if "user" in turns:
        opening = (
            ActivityTurn.objects.filter(turn="user", **common).order_by("-created_at").first()
        )

    feedback = None
    if "feedback" in turns:
        feedback = (
            ActivityTurn.objects.filter(turn="feedback", **common)
            .order_by("-created_at")
            .first()
        )

    brief = build_brief(activity, text, level, reply_language, prompts) if "brief" in turns else ""
    has_box = "feedback" in turns and ("user" not in turns or opening is not None)

    notes = []
    if activity.render == "annotated" and opening:
        notes = parse_notes(opening.content)
        locate_notes(text.body, notes)

    context = {
        "session": session,
        "activity": activity,
        "activities": config.activities,
        "levels": config.levels,
        "level": level,
        "reply_language": reply_language,
        "reply_choices": _reply_choices(activity, text),
        "text": text,
        "turns": turns,
        "opening": opening,
        "feedback": feedback,
        "brief": brief,
        "has_box": has_box,
        "notes": notes,
        "body_html": mark_safe(body_html(text.body, notes)),
        "notes_html": render_markdown(notes_markdown(notes)) if notes else "",
        "placed_count": sum(1 for n in notes if n.located),
        "query": _query(level.id, reply_language),
    }
    return render(request, "reading/read.html", context)


def _stream_and_save(*, session, activity_id, turn, level_id, reply_language, model, system, user, options, draft="", cache_key=None):
    """A StreamingHttpResponse body that saves the full reply once it ends.

    With ``cache_key`` the finished reply is also stored in the shared
    CachedReply table (never for errors or empty replies).
    """
    buffer: list[str] = []
    try:
        for piece in stream_reply(model, system, user, options):
            buffer.append(piece)
            yield piece
    except LLMError as exc:
        yield f"\n\n**Something went wrong:** {exc}"
        return
    content = "".join(buffer)
    ActivityTurn.objects.create(
        session=session,
        activity_id=activity_id,
        turn=turn,
        level_id=level_id,
        reply_language=reply_language,
        model=model,
        draft=draft,
        content=content,
    )
    if cache_key and content.strip():
        CachedReply.store(
            key=cache_key, activity_id=activity_id, level_id=level_id,
            reply_language=reply_language, model=model,
            source_ref=session.source_ref, content=content,
        )


@require_POST
def generate_view(request, pk: int, activity_id: str):
    session = _get_session(request, pk)
    config = _config()
    prompts = load_prompts()
    activity = _get_activity(activity_id, config)
    if "user" not in available_templates(activity.id, prompts):
        return HttpResponseBadRequest("This activity has no opening turn to generate.")

    level = _resolved_level(request, config)
    text = _session_to_text(session)
    reply_language = _resolved_reply(request, activity, text)
    system, user = build_messages(activity, text, level, reply_language, prompts, turn="user")
    model = config.model_for(text.lang)
    options = config.models.get("options", {})

    # One stored result per activity / level / reply language, per reader: once an
    # opening exists the reader cannot generate another (the page hides the
    # button; this refuses a stale tab or a hand-made request too). Reset
    # clears it, and regenerating after a Reset costs nothing — the shared
    # cache below serves the stored reply.
    if ActivityTurn.objects.filter(
        session=session, activity_id=activity.id, turn="user",
        level_id=level.id, reply_language=reply_language,
    ).exists():
        return HttpResponse(
            "You already have a result for this activity — reload the page to see it.",
            status=409, content_type="text/plain; charset=utf-8",
        )

    # Shared reply cache. Library texts only (an upload is private to its
    # reader and rarely repeats).
    cache_key = None
    if not session.uploaded:
        cache_key = CachedReply.make_key(model, system, user, options)
        cached = CachedReply.objects.filter(key=cache_key).first()
        if cached:
            CachedReply.objects.filter(pk=cached.pk).update(hits=F("hits") + 1)
            ActivityTurn.objects.create(
                session=session, activity_id=activity.id, turn="user",
                level_id=level.id, reply_language=reply_language,
                model=model, content=cached.content,
            )
            return HttpResponse(cached.content, content_type="text/plain; charset=utf-8")

    body = _stream_and_save(
        session=session, activity_id=activity.id, turn="user",
        level_id=level.id, reply_language=reply_language,
        model=model, system=system, user=user, options=options,
        cache_key=cache_key,
    )
    return StreamingHttpResponse(body, content_type="text/plain; charset=utf-8")


@require_POST
def submit_view(request, pk: int, activity_id: str):
    session = _get_session(request, pk)
    config = _config()
    prompts = load_prompts()
    activity = _get_activity(activity_id, config)
    if "feedback" not in available_templates(activity.id, prompts):
        return HttpResponseBadRequest("This activity has no feedback turn.")

    draft = (request.POST.get("draft") or "").strip()
    if not draft:
        return HttpResponseBadRequest("Write something first.")

    level = _resolved_level(request, config)
    text = _session_to_text(session)
    reply_language = _resolved_reply(request, activity, text)
    opening = (
        ActivityTurn.objects.filter(
            session=session, activity_id=activity.id, turn="user",
            level_id=level.id, reply_language=reply_language,
        )
        .order_by("-created_at")
        .first()
    )
    system, user = build_messages(
        activity, text, level, reply_language, prompts, turn="feedback",
        draft=draft, questions=opening.content if opening else "",
    )
    model = config.model_for(text.lang)
    options = config.models.get("options", {})

    body = _stream_and_save(
        session=session, activity_id=activity.id, turn="feedback",
        level_id=level.id, reply_language=reply_language,
        model=model, system=system, user=user, options=options, draft=draft,
    )
    return StreamingHttpResponse(body, content_type="text/plain; charset=utf-8")


def history_view(request):
    config = _config()
    labels = {a.id: a.label for a in config.activities}

    sessions_data = []
    if settings.AUTH_REQUIRED or _session_key(request):
        sessions = (
            ReadingSession.objects.filter(**_owner(request))
            .prefetch_related("turns")
            .order_by("-created_at")
        )
        for session in sessions:
            activities: dict[str, dict] = {}
            for turn in session.turns.all():  # already ordered -created_at
                entry = activities.setdefault(
                    turn.activity_id,
                    {"label": labels.get(turn.activity_id, turn.activity_id), "count": 0, "latest": turn.created_at},
                )
                entry["count"] += 1
            sessions_data.append({"session": session, "activities": activities.values()})

    return render(request, "reading/history.html", {"sessions_data": sessions_data})
