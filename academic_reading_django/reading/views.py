"""Views for the reading app.

Server-rendered, session-scoped, no accounts. The reading logic itself
(corpus/prompts/annotate/languages/llm) is ported nearly verbatim from the
original Streamlit app's lib/ package into reading/logic/ — see that
package for the real work; these views are mostly plumbing between it and
the ReadingSession/ActivityTurn history tables.
"""

from __future__ import annotations

import hashlib

from django.contrib import messages
from django.http import Http404, HttpResponseBadRequest, StreamingHttpResponse
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .logic.annotate import body_html, locate_notes, notes_markdown, parse_notes
from .logic.corpus import Text, load_library, text_from_upload
from .logic.languages import resolve
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


def _get_session(request, pk: int) -> ReadingSession:
    return get_object_or_404(ReadingSession, pk=pk, session_key=_session_key(request))


def _get_activity(activity_id: str, config: Config) -> Activity:
    for activity in config.activities:
        if activity.id == activity_id:
            return activity
    raise Http404("Unknown activity.")


def _session_to_text(session: ReadingSession) -> Text:
    return Text(
        id=session.source_ref,
        lang=session.language_code,
        title=session.title,
        body=session.body,
        author=session.author,
        language=session.language_name,
        level_value=session.level_id,
        source=session.source,
        notes=session.notes,
        file="",
        uploaded=session.uploaded,
        script=session.script,
    )


# --------------------------------------------------------------------------- #
# Library / upload
# --------------------------------------------------------------------------- #
def home_view(request):
    config = _config()
    texts, problems = load_library(config)
    languages = sorted({t.language_name for t in texts})

    history = []
    session_key = _session_key(request)
    if session_key:
        history = list(
            ReadingSession.objects.filter(session_key=session_key).order_by("-created_at")
        )

    return render(
        request,
        "reading/home.html",
        {
            "texts": texts,
            "problems": problems,
            "languages": languages,
            "history": history,
        },
    )


def open_view(request, source_ref: str):
    config = _config()
    texts, _ = load_library(config)
    text = next((t for t in texts if t.id == source_ref), None)
    if text is None:
        raise Http404("Text not found.")

    _ensure_session_key(request)
    level = config.level(text.level_value)
    session, _created = ReadingSession.objects.get_or_create(
        session_key=request.session.session_key,
        source_ref=f"lib:{text.id}",
        defaults=dict(
            title=text.title,
            author=text.author,
            language_code=text.lang,
            language_name=text.language_name,
            level_id=level.id,
            script=text.script,
            body=text.body,
            source=text.source,
            notes=text.notes,
            uploaded=False,
        ),
    )
    return redirect("reading:activity", pk=session.pk, activity_id=config.activities[0].id)


@require_POST
def upload_view(request):
    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Choose a file to upload.")
        return redirect("reading:home")

    config = _config()
    text = text_from_upload(upload.name, upload.read(), config)

    chosen_language = (request.POST.get("language") or "").strip()
    if chosen_language and chosen_language != text.language_name:
        code, name = resolve(chosen_language)
        if code:
            text.lang, text.language = code, name

    _ensure_session_key(request)
    level = config.level(text.level_value)
    source_ref = "upload:" + hashlib.sha1(text.body.encode("utf-8")).hexdigest()[:16]
    session, _created = ReadingSession.objects.get_or_create(
        session_key=request.session.session_key,
        source_ref=source_ref,
        defaults=dict(
            title=text.title,
            author="",
            language_code=text.lang,
            language_name=text.language_name,
            level_id=level.id,
            script=text.script,
            body=text.body,
            source="",
            notes="",
            uploaded=True,
        ),
    )
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
    level = config.level(session.level_id)
    text = _session_to_text(session)
    turns = available_templates(activity.id, prompts)

    opening = None
    if "user" in turns:
        opening = (
            ActivityTurn.objects.filter(session=session, activity_id=activity.id, turn="user")
            .order_by("-created_at")
            .first()
        )

    feedback = None
    if "feedback" in turns:
        feedback = (
            ActivityTurn.objects.filter(session=session, activity_id=activity.id, turn="feedback")
            .order_by("-created_at")
            .first()
        )

    brief = build_brief(activity, text, level, prompts) if "brief" in turns else ""
    has_box = "feedback" in turns and ("user" not in turns or opening is not None)

    notes = []
    if activity.render == "annotated" and opening:
        notes = parse_notes(opening.content)
        locate_notes(text.body, notes)

    context = {
        "session": session,
        "activity": activity,
        "activities": config.activities,
        "level": level,
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
    }
    return render(request, "reading/read.html", context)


def _stream_and_save(*, session, activity_id, turn, model, system, user, options, draft="", cache_key=None):
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
        model=model,
        draft=draft,
        content=content,
    )
    if cache_key and content.strip():
        CachedReply.store(
            key=cache_key, activity_id=activity_id, level_id=session.level_id,
            reply_language="", model=model,
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

    level = config.level(session.level_id)
    text = _session_to_text(session)
    system, user = build_messages(activity, text, level, prompts, turn="user")
    model = config.model_for(text.lang)
    options = config.models.get("options", {})

    # One stored result per activity, per reader: once an
    # opening exists the reader cannot generate another (the page hides the
    # button; this refuses a stale tab or a hand-made request too). Reset
    # clears it, and regenerating after a Reset costs nothing — the shared
    # cache below serves the stored reply.
    if ActivityTurn.objects.filter(
        session=session, activity_id=activity.id, turn="user",
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
                model=model, content=cached.content,
            )
            return HttpResponse(cached.content, content_type="text/plain; charset=utf-8")

    body = _stream_and_save(
        session=session, activity_id=activity.id, turn="user",
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

    level = config.level(session.level_id)
    text = _session_to_text(session)
    opening = (
        ActivityTurn.objects.filter(session=session, activity_id=activity.id, turn="user")
        .order_by("-created_at")
        .first()
    )
    system, user = build_messages(
        activity, text, level, prompts, turn="feedback",
        draft=draft, questions=opening.content if opening else "",
    )
    model = config.model_for(text.lang)
    options = config.models.get("options", {})

    body = _stream_and_save(
        session=session, activity_id=activity.id, turn="feedback",
        model=model, system=system, user=user, options=options, draft=draft,
    )
    return StreamingHttpResponse(body, content_type="text/plain; charset=utf-8")


def history_view(request):
    session_key = _session_key(request)
    config = _config()
    labels = {a.id: a.label for a in config.activities}

    sessions_data = []
    if session_key:
        sessions = (
            ReadingSession.objects.filter(session_key=session_key)
            .prefetch_related("turns")
            .order_by("-created_at")
        )
        for session in sessions:
            activities: dict[str, dict] = {}
            for turn in session.turns.all():  # already ordered -created_at
                entry = activities.setdefault(
                    turn.activity_id, {"label": labels.get(turn.activity_id, turn.activity_id), "count": 0, "latest": turn.created_at}
                )
                entry["count"] += 1
            sessions_data.append({"session": session, "activities": activities.values()})

    return render(request, "reading/history.html", {"sessions_data": sessions_data})
