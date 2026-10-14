"""Building prompts from prompts.yaml.

An activity is up to three turns, and declares which it has by which templates
it defines:

    user      the model's opening turn — questions to answer, or a finished
              piece of work for activities that need no input from the reader
    brief     what the reader is asked to write, rendered by the app with no
              model call at all
    feedback  the model's response to what the reader wrote

Everything the model writes is in English, so there is no reply-language to
thread through. The level is a property of the text rather than of the reader,
and it does the job the reader's declared level did in version 1: it decides
how much gets explained.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

import yaml

from .corpus import Text
from .settings import ROOT, Activity, Level

PROMPTS_PATH = ROOT / "prompts.yaml"

TEMPLATES = ("user", "brief", "feedback")

DRAFT_OPEN = "--- THE READER'S OWN WRITING BEGINS ---"
DRAFT_CLOSE = "--- THE READER'S OWN WRITING ENDS ---"

METADATA_NOTE_CATALOGUE = (
    "The heading above is what the app's own catalogue records, which is only "
    "as complete as whoever filed the text made it. What it states you may rely "
    "on. What it omits you do not know — where it gives no author, no date or "
    "no occasion, work from the text itself and say nothing you cannot see "
    "there. In particular, an author's name is not a date: do not date the text "
    "from who wrote it."
)
METADATA_NOTE_UPLOAD = (
    "This text was uploaded and carries no catalogue entry at all. Its title is "
    "a filename and its language was guessed by the app. Work out what you can "
    "from the text itself, and say nothing about its author, date or provenance "
    "unless the text states it. Do not guess."
)


def load_prompts(path: Path = PROMPTS_PATH) -> dict:
    """Read prompts.yaml. Called per generation so edits apply immediately."""
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _fill(template: str, values: dict) -> str:
    return Template(template or "").safe_substitute(values)


def _spec_values(spec: dict, level: Level) -> dict:
    """Knobs declared alongside the templates, ready to substitute.

    Every key in an activity's block that is not itself a template becomes a
    placeholder of the same name. A plain value is used as it stands; a mapping
    keyed by level id is resolved for this text's level, and a level the mapping
    does not name resolves to nothing. That is how an optional section such as
    ``first_pass`` appears at one level and vanishes at the others — and it
    means prompts.yaml can grow a new knob without a change here.
    """
    values = {}
    for key, value in spec.items():
        if key in TEMPLATES:
            continue
        if isinstance(value, dict):
            value = value.get(level.id, "")
        values[key] = value.strip() if isinstance(value, str) else value
    return values


def available_templates(activity_id: str, prompts: dict | None = None) -> set[str]:
    """Which of the three turns this activity actually defines."""
    prompts = prompts or load_prompts()
    spec = prompts.get("activities", {}).get(activity_id, {})
    return {key for key in TEMPLATES if key in spec}


def describe(text: Text) -> str:
    """The heading every template puts above the text.

    Assembled here rather than repeated in ten templates, and it omits what it
    does not know instead of printing "not stated" — a blank line invites less
    invention than an explicit gap does.
    """
    lines = [f"Title: {text.title}"]
    if text.author:
        lines.append(f"Author: {text.author}")
    lines.append(f"Language: {text.language_name}")
    if text.detected:
        lines[-1] += " (detected by the app, not stated by the cataloguer)"
    if text.script:
        lines.append(f"Script: {text.script} characters")
    lines.append(f"Length: {text.length} {text.length_unit}")
    if text.source:
        lines.append(f"Source: {text.source}")
    if text.notes:
        lines.append(f"Cataloguer's notes: {text.notes}")
    return "\n".join(lines)


def _values(
    activity: Activity,
    text: Text,
    level: Level,
    prompts: dict,
    draft: str = "",
    questions: str = "",
) -> dict:
    """Everything an activity's templates can substitute."""
    shared = prompts["shared"]
    spec = prompts["activities"][activity.id]

    base = {"language": text.language_name, "level_label": level.label}

    notes = shared.get("language_notes", {})
    language_notes = _fill(
        notes.get(text.lang) or notes.get("default", ""),
        {"script": text.script or "unspecified", **base},
    )

    columns = shared.get("vocab_columns", {})
    values = {
        **_spec_values(spec, level),
        **base,
        "metadata": describe(text),
        "metadata_note": METADATA_NOTE_UPLOAD if text.uploaded else METADATA_NOTE_CATALOGUE,
        "text": text.body,
        "title": text.title,
        "length": text.length,
        "length_unit": text.length_unit,
        "level_guidance": _fill(shared["level_guidance"][level.id], base).strip(),
        "language_notes": language_notes.strip(),
        "vocab_columns": columns.get(
            "romanised" if text.needs_romanisation else "latin", ""
        ),
        "romanisation_note": (
            shared.get("romanisation_note", "").strip()
            if text.needs_romanisation
            else ""
        ),
        "draft": f"{DRAFT_OPEN}\n{draft.strip()}\n{DRAFT_CLOSE}",
        "questions": questions.strip(),
    }

    # Shared sections that templates pull in whole, filled after the rest so
    # they can use the activity's own knobs.
    for name in ("question_marking",):
        values[name] = _fill(shared.get(name, ""), values).strip()
    return values


def build_messages(
    activity: Activity,
    text: Text,
    level: Level,
    prompts: dict | None = None,
    turn: str = "user",
    draft: str = "",
    questions: str = "",
) -> tuple[str, str]:
    """Return (system, user) for one turn of an activity.

    ``turn`` is ``user`` for the model's opening turn and ``feedback`` for its
    response to the reader's writing, which arrives as ``draft``. A marking
    turn also needs ``questions`` — the opening turn's own output, which the
    model has to see again to mark answers against it.
    """
    prompts = prompts or load_prompts()
    shared = prompts["shared"]
    values = _values(activity, text, level, prompts, draft, questions)

    # A marking turn always discusses content: withholding the answer from a
    # reader whose answer you are correcting would be absurd. The activity's own
    # spoilers flag governs its opening turn only.
    spoilers = activity.spoilers or turn == "feedback"
    rules = [shared["spoiler_rule"]["allow" if spoilers else "forbid"].strip()]
    if turn == "feedback":
        rules.append(shared["draft_rule"].strip())

    system = _fill(
        shared["system"],
        {
            **values,
            "reading_stance": shared["reading_stance"][activity.stance],
            "spoiler_rule": "\n\n".join(rules),
        },
    )
    return system.strip(), _fill(prompts["activities"][activity.id][turn], values).strip()


def build_brief(
    activity: Activity,
    text: Text,
    level: Level,
    prompts: dict | None = None,
) -> str:
    """What the reader is asked to write. No model is involved."""
    prompts = prompts or load_prompts()
    spec = prompts["activities"][activity.id]
    if "brief" not in spec:
        return ""
    return _fill(spec["brief"], _values(activity, text, level, prompts)).strip()
