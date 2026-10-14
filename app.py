"""Academic Reading v2 — a reading-skills tutor for texts in any language.

Everything the app says is in English, whatever the text is written in, so
there is no reply-language control and no declared reader level. The level
belongs to the text and comes from source.cfg.

An activity is up to three turns — the model opens, the reader writes, the
model responds — and prompts.yaml declares which of them each activity has, so
this file needs no per-activity branching beyond the one activity that draws
its output into the reading text (9, close commentary).
"""

from __future__ import annotations

import hashlib
import html

import streamlit as st

from lib.annotate import body_html, locate_notes, notes_markdown, parse_notes
from lib.corpus import (
    Text,
    corpus_signature,
    count_length,
    load_library,
    text_from_upload,
)
from lib.languages import NAMES, name_of
from lib.llm import LLMError, stream_reply
from lib.prompts import available_templates, build_brief, build_messages, load_prompts
from lib.settings import cloud_api_key, load_config

st.set_page_config(page_title="Academic Reading", page_icon="📖", layout="wide")

CONFIG = load_config()
READING = CONFIG.reading

# Re-read on every rerun, so edits to prompts.yaml take effect immediately.
PROMPTS = load_prompts()

# The pane and the box the reader writes in share one height budget, so both
# columns come out the same height whatever the activity is doing.
PANE_PX = READING.get("pane_height_px", 640)
SPLIT_PX = round(PANE_PX * READING.get("work_split", 0.58))
DRAFT_PX = max(PANE_PX - SPLIT_PX - 32, READING.get("draft_min_px", 180))


@st.cache_data(show_spinner=False)
def library(signature: tuple):
    """The corpus, reloaded whenever `signature` changes.

    The signature is the argument that makes the cache correct rather than
    merely fast: it changes when a file in sources/ or the catalogue changes, so
    a text added while the app is running shows up on the next rerun.
    """
    return load_library(CONFIG)


TEXTS, PROBLEMS = library(corpus_signature(CONFIG))


def digest(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #
st.markdown(
    f"""
    <style>
      .reading-body {{
        font-family: Georgia, "Times New Roman", serif;
        font-size: {READING.get("font_size_px", 17)}px;
        line-height: {READING.get("line_height", 1.75)};
        text-align: left;
      }}
      .reading-body.cjk {{
        font-family: "Songti SC", "STSong", "PingFang SC", serif;
        font-size: {READING.get("cjk_font_size_px", 20)}px;
        line-height: 2.0;
      }}
      .reading-body p {{ margin: 0 0 1.05em 0; }}
      /* Close commentary: the anchored phrase, and its number after it. */
      .reading-body .anno {{ border-bottom: 1px dashed rgba(200,140,0,0.85); }}
      .reading-body .anno-num {{
        font-size: 0.68em; font-weight: 700; padding-left: 1px;
        color: rgba(200,140,0,1); vertical-align: super; line-height: 0;
      }}
      .badge {{
        display: inline-block; padding: 1px 9px; margin: 0 6px 6px 0;
        border-radius: 11px; font-size: 12px; line-height: 19px;
        border: 1px solid rgba(128,128,128,0.35); opacity: 0.9;
      }}
      .badge.warn {{ border-color: rgba(200,140,0,0.65); }}
      /* Model output: markdown headings shrunk to pane scale. The model is
         asked for ## and ###; h1 is here because a model that ignores that and
         writes a title should still not blow the pane apart. */
      [data-testid="stMain"] [data-testid="stHeadingWithActionElements"] h1 {{
        font-size: 1.15rem !important; font-weight: 600 !important;
        padding: 0.6rem 0 0.1rem 0 !important;
      }}
      [data-testid="stMain"] [data-testid="stHeadingWithActionElements"] h2 {{
        font-size: 1.05rem !important; font-weight: 600 !important;
        padding: 0.8rem 0 0.1rem 0 !important;
      }}
      [data-testid="stMain"] [data-testid="stHeadingWithActionElements"] h3 {{
        font-size: 0.96rem !important; font-weight: 600 !important;
        padding: 0.5rem 0 0.1rem 0 !important;
      }}
      [data-testid="stMarkdown"] table {{ font-size: 0.86rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def badge(label: str, warn: bool = False) -> str:
    cls = "badge warn" if warn else "badge"
    return f'<span class="{cls}">{html.escape(label)}</span>'


def language_picker(label: str, current: str, key: str) -> str:
    """A language chooser that accepts anything, not only what we can detect."""
    known = sorted(NAMES.values())
    options = known if current in (None, "") else [name_of(current)] + [
        n for n in known if n != name_of(current)
    ]
    return st.selectbox(label, options, key=key)


# --------------------------------------------------------------------------- #
# Sidebar — text, activity, model
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("📖 Academic Reading")

    st.subheader("Text")
    source = st.radio(
        "Where from", ["Library", "Upload your own"], horizontal=True,
        label_visibility="collapsed",
    )

    text: Text | None = None

    if source == "Library":
        if not TEXTS:
            st.warning(
                f"No texts found. Put `.txt` or `.md` files in "
                f"`{CONFIG.texts.get('directory', 'sources')}/`."
            )
        else:
            languages = sorted({t.language_name for t in TEXTS})
            chosen = st.selectbox("Language", ["All"] + languages)
            pool = [t for t in TEXTS if chosen == "All" or t.language_name == chosen]
            text = st.selectbox(
                "Text", pool, format_func=lambda t: t.title,
            )
    else:
        upload = st.file_uploader("A text or markdown file", type=["txt", "md", "markdown"])
        if upload is not None:
            text = text_from_upload(upload.name, upload.getvalue(), CONFIG)
            if text.lang:
                st.caption(
                    f"Detected **{text.language_name}** "
                    f"({text.confidence:.0%} confident)"
                )
            else:
                st.warning("Could not detect the language — please choose it.")
            picked = language_picker(
                "Language", text.lang, f"upload_lang_{digest(text.body)}"
            )
            if picked != text.language_name:
                from lib.languages import resolve

                text.lang, text.language = resolve(picked)

    if PROBLEMS:
        with st.expander(f"⚠️ {len(PROBLEMS)} catalogue problem(s)"):
            for problem in PROBLEMS:
                st.markdown(f"- {problem}")

    st.divider()

    st.subheader("Activity")
    activity = st.radio(
        "Activity",
        CONFIG.activities,
        format_func=lambda a: a.display,
        label_visibility="collapsed",
    )

    st.divider()

    with st.expander("Model", expanded=False):
        backend = st.radio(
            "Backend", CONFIG.backends, horizontal=True,
            format_func=lambda b: {"local": "Local", "cloud": "Cloud"}[b],
            index=CONFIG.backends.index(CONFIG.backend),
        )
        if backend == "cloud" and not cloud_api_key():
            st.warning("No `OLLAMA_API_KEY` found in `.env`.")

        routed = CONFIG.model_for(text.lang, backend) if text and text.lang else ""
        options = CONFIG.alternatives(backend)
        if routed and routed not in options:
            options = [routed] + options
        default_label = f"Automatic{f' — {routed}' if routed else ''}"
        model = st.selectbox("Model", ["__auto__"] + options,
                             format_func=lambda m: default_label if m == "__auto__" else m)
        if model == "__auto__":
            model = routed


if text is None:
    st.info(
        "Choose a text from the library, or upload one, to begin. Library texts "
        f"live in `{CONFIG.texts.get('directory', 'sources')}/` and are described "
        f"in `{CONFIG.texts.get('catalogue', 'source.cfg')}`."
    )
    st.stop()


# --------------------------------------------------------------------------- #
# State — worked out before either column is drawn, because activity 9's
# output has to be marked into the reading text on the left.
# --------------------------------------------------------------------------- #
level = CONFIG.level(text.level_value)
turns = available_templates(activity.id, PROMPTS)
body_id = digest(text.body)

# The draft is keyed on the text and activity only. Deliberately not on the
# backend or model: changing either must not throw away what the reader wrote.
draft_key = f"draft_{body_id}_{activity.id}"
draft = st.session_state.get(draft_key, "")

results = st.session_state.setdefault("results", {})


def result_key(turn: str, *extra: str) -> tuple:
    return (body_id, activity.id, turn, level.id, backend, model, *extra)


opening = results.get(result_key("user")) if "user" in turns else None
brief = build_brief(activity, text, level, PROMPTS) if "brief" in turns else ""

# Marking depends on the questions as well as the answers, so both are in the
# key: new questions, or an edited answer, invalidate the old marking.
feedback_key = result_key("feedback", digest(draft), digest(opening or ""))
feedback = results.get(feedback_key) if "feedback" in turns and draft.strip() else None

# The box appears as soon as there is something to write against — immediately
# for the activities that open with a brief, and once the questions exist for
# the ones that open with a model turn.
has_box = "feedback" in turns and ("user" not in turns or opening is not None)

notes = []
if activity.render == "annotated" and opening:
    notes = parse_notes(opening)
    locate_notes(text.body, notes)


# --------------------------------------------------------------------------- #
# Main — text on the left, activity on the right
# --------------------------------------------------------------------------- #
reading_col, work_col = st.columns([1.15, 1], gap="large")

with reading_col:
    st.markdown(f"### {text.title}")
    if text.author:
        st.caption(text.author)

    badges = [
        badge(text.language_name, warn=text.detected),
        badge(f"{text.length} {text.length_unit}", warn=bool(text.warnings)),
        badge(level.label),
    ]
    if text.script:
        badges.append(badge(f"{text.script} 字", warn=text.script == "traditional"))
    if text.uploaded:
        badges.append(badge("uploaded"))
    st.markdown("".join(badges), unsafe_allow_html=True)

    for warning in text.warnings:
        st.warning(warning, icon="⚠️")
    if text.detected and not text.uploaded:
        st.info(
            f"`source.cfg` does not give a language for this text, so the app "
            f"guessed **{text.language_name}**. Add a `language =` line if that "
            f"is wrong.",
            icon="ℹ️",
        )

    with st.container(height=PANE_PX, border=True):
        st.markdown(
            f'<div class="reading-body{" cjk" if text.is_cjk else ""}">'
            f"{body_html(text.body, notes)}</div>",
            unsafe_allow_html=True,
        )

    if notes:
        placed = sum(1 for n in notes if n.located)
        st.caption(
            f"{placed} passage{'' if placed == 1 else 's'} marked — the numbered "
            "comments are on the right."
        )
    else:
        trail = [text.notes, f"Source: {text.source}" if text.source else ""]
        line = " · ".join(bit for bit in trail if bit)
        if line:
            st.caption(line)

with work_col:
    st.markdown(f"### {activity.label}")
    st.caption(activity.description)

    # The model's opening turn. Activities that begin with a brief have no
    # button here, because there is nothing to ask the model for yet.
    run_opening = False
    if "user" in turns:
        if "feedback" in turns:
            label = "New questions" if opening else "Generate questions"
        else:
            label = "Regenerate" if opening else "Generate"
        run_opening = st.button(
            label, type="primary", use_container_width=True, disabled=not model
        )
    elif not turns:
        st.button("Generate", use_container_width=True, disabled=True)

    pane = st.container(height=SPLIT_PX if has_box else PANE_PX, border=True)

    # The reader's turn. A form, so ⌘⏎ in the box sends it.
    submitted = False
    if has_box:
        with st.form(f"write_{activity.id}", border=False):
            st.text_area(
                "Your writing",
                key=draft_key,
                height=DRAFT_PX,
                label_visibility="collapsed",
                placeholder="Write here, in English — ⌘⏎ (Ctrl+Enter) to send.",
            )
            # The box is inside a form, so its contents only reach the app on
            # submit — this counts what was last sent, not what is being typed.
            written = count_length(draft, "en")
            st.caption(f"{written} words sent." if written else "Nothing sent yet.")
            submitted = st.form_submit_button(
                activity.submit_label,
                type="primary",
                use_container_width=True,
                disabled=not model,
            )

    def run(turn: str, key: tuple, **kwargs) -> None:
        """Stream one turn into the pane and cache it under `key`."""
        system, user = build_messages(activity, text, level, PROMPTS, turn, **kwargs)
        try:
            with pane:
                answer = st.write_stream(
                    stream_reply(
                        backend, model, system, user, CONFIG.models.get("options", {})
                    )
                )
            results[key] = answer
            st.rerun()  # redraw from cache, with the annotations and new labels
        except LLMError as exc:
            pane.error(str(exc))

    if run_opening:
        run("user", result_key("user"))
    elif submitted:
        fresh = st.session_state.get(draft_key, "")
        if not fresh.strip():
            pane.warning("Write something first.")
        else:
            run(
                "feedback",
                result_key("feedback", digest(fresh), digest(opening or "")),
                draft=fresh,
                questions=opening or "",
            )
    elif feedback:
        pane.markdown(feedback)
    elif notes:
        pane.markdown(notes_markdown(notes))
    elif opening:
        pane.markdown(opening)
    elif brief:
        pane.markdown(brief)
    elif turns:
        pane.markdown(
            f"*Ready — this text is filed as **{level.label}**, "
            f"using **{model or 'no model configured'}**.*"
        )
    else:
        pane.markdown(
            f"*Activity **{activity.number}. {activity.label}** is not wired up yet.*"
        )

    latest = feedback or opening
    if latest:
        with st.expander("📋 Copy as text"):
            st.code(latest, language="markdown")
