"""Building prompts from prompts.yaml.

An activity is up to three turns, and declares which of them it has by which
templates it defines:

    user      the model's opening turn — questions to answer, or a finished
              piece of work for activities that need no input from the student
    brief     what the student is asked to write, rendered by the app with no
              model call at all
    feedback  the model's response to what the student wrote

A one-shot activity has only ``user``; activities 2 and 3 have ``user`` and
``feedback``; activities 5 and 6 have ``brief`` and ``feedback``.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

import yaml

from .corpus import Text
from .settings import ROOT, Activity, Level

PROMPTS_PATH = ROOT / "prompts.yaml"

TEMPLATES = ("user", "brief", "feedback")

UNKNOWN = "not stated"

DRAFT_OPEN = "--- THE STUDENT'S OWN WRITING BEGINS ---"
DRAFT_CLOSE = "--- THE STUDENT'S OWN WRITING ENDS ---"

METADATA_NOTE_LIBRARY = (
    "The metadata above is reliable and comes from the app's own catalogue."
)
METADATA_NOTE_UPLOAD = (
    "This text was uploaded by the student and carries no reliable metadata. "
    "Work out what you can from the text itself, and say nothing about its "
    "author, date or provenance unless the text states it. Do not guess."
)


def load_prompts(path: Path = PROMPTS_PATH) -> dict:
    """Read prompts.yaml. Called per generation so edits apply immediately."""
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _fill(template: str, values: dict) -> str:
    return Template(template).safe_substitute(values)


def _spec_values(spec: dict, level: Level, budget_scale: float = 1.0) -> dict:
    """Knobs declared alongside the templates, ready to substitute.

    Every key in an activity's block that is not itself a template becomes a
    placeholder of the same name. A plain value is used as it stands; a mapping
    keyed by level id is resolved for this student's level, and a level the
    mapping does not name resolves to nothing. That is how an optional section
    such as ``first_pass`` appears for one level and vanishes for the others —
    and it means prompts.yaml can grow a new knob without a change here.
    """
    values = {}
    for key, value in spec.items():
        if key in TEMPLATES:
            continue
        if isinstance(value, dict):
            value = value.get(level.id, "")
        if isinstance(value, str):
            value = value.strip()
        elif key.endswith("budget") and budget_scale != 1.0:
            value = round(value * budget_scale / 10) * 10
        values[key] = value
    return values


def available_templates(activity_id: str, prompts: dict | None = None) -> set[str]:
    """Which of the three turns this activity actually defines."""
    prompts = prompts or load_prompts()
    spec = prompts.get("activities", {}).get(activity_id, {})
    return {key for key in TEMPLATES if key in spec}


def _values(
    activity: Activity,
    text: Text,
    level: Level,
    reply_language: str,
    prompts: dict,
    draft: str = "",
    questions: str = "",
) -> dict:
    """Everything an activity's templates can substitute."""
    shared = prompts["shared"]
    spec = prompts["activities"][activity.id]

    base = {
        "language": text.language_name,
        "level_label": level.label,
        "level_cefr": level.cefr,
        "reply_language": reply_language,
    }

    language_notes = _fill(
        shared["language_notes"].get(text.lang, ""),
        {
            "script": text.script or "unspecified",
            "register": text.register or "unspecified",
            **base,
        },
    )

    script_line = ""
    if text.lang == "zh" and text.script:
        register = f", register: {text.register}" if text.register else ""
        script_line = f"\nScript: {text.script} characters{register}"

    # Budgets count the units of the language being WRITTEN, not the language
    # being read: an English answer about a Chinese text is measured in English
    # words and needs no scaling.
    in_target = reply_language == text.language_name
    budget_unit = text.length_unit if in_target else "words"
    scale = float(shared.get("budget_scale", {}).get(text.lang, 1)) if in_target else 1.0

    values = {
        **_spec_values(spec, level, scale),
        **base,
        "title": text.title or UNKNOWN,
        "author": text.author or UNKNOWN,
        "year": str(text.year) if text.year else UNKNOWN,
        "topic": text.topic or UNKNOWN,
        "text": text.body,
        "script_line": script_line,
        "length": text.length,
        "length_unit": text.length_unit,
        "budget_unit": budget_unit,
        "level_guidance": _fill(shared["level_guidance"][level.id], base).strip(),
        "language_notes": language_notes.strip(),
        "metadata_note": METADATA_NOTE_UPLOAD if text.uploaded else METADATA_NOTE_LIBRARY,
        "vocab_columns": shared.get("vocab_columns", {}).get(text.lang, ""),
        "draft": f"{DRAFT_OPEN}\n{draft.strip()}\n{DRAFT_CLOSE}",
        "questions": questions.strip(),
    }

    # Shared sections that templates pull in whole. Filled in dependency order:
    # the marking block quotes the language table, which needs the activity's
    # own row count.
    for name in ("language_table", "question_marking"):
        values[name] = _fill(shared.get(name, ""), values).strip()
    return values


def build_messages(
    activity: Activity,
    text: Text,
    level: Level,
    reply_language: str,
    prompts: dict | None = None,
    turn: str = "user",
    draft: str = "",
    questions: str = "",
) -> tuple[str, str]:
    """Return (system, user) for one turn of an activity.

    ``turn`` is ``user`` for the model's opening turn and ``feedback`` for its
    response to the student's writing, which arrives as ``draft``. A marking
    turn also needs ``questions`` — the opening turn's own output, which the
    model has to see again to mark answers against it.
    """
    prompts = prompts or load_prompts()
    shared = prompts["shared"]
    values = _values(activity, text, level, reply_language, prompts, draft, questions)

    # A marking turn always discusses content: withholding the answer from a
    # student whose answer you are correcting would be absurd. The activity's
    # own spoilers flag governs its opening turn only.
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
    reply_language: str,
    prompts: dict | None = None,
) -> str:
    """What the student is asked to write. No model is involved."""
    prompts = prompts or load_prompts()
    spec = prompts["activities"][activity.id]
    if "brief" not in spec:
        return ""
    values = _values(activity, text, level, reply_language, prompts)
    return _fill(spec["brief"], values).strip()
