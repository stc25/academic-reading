"""Close commentary: anchored notes, and marking them into the reading text.

The model is asked for blocks of

    ANCHOR: <a phrase copied from the text>
    NOTE:   <the comment on it>

rather than for a rewritten copy of the text with comments inserted. The text
itself then never passes through the model, so it cannot come back paraphrased,
reordered or silently shortened. An anchor the model invented simply fails to
locate, and its note is reported separately instead of corrupting the reading
pane.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_BLOCK = re.compile(r"^[ \t]*ANCHOR:[ \t]*", re.M)
_NOTE = re.compile(r"^[ \t]*NOTE:[ \t]*", re.M)
_QUOTES = "«»“”„‟\"'‘’ 「」『』"

# Typography a model silently improves when it quotes: a hyphen becomes an em
# dash, oe becomes the ligature, a straight apostrophe becomes a curly one.
# Folded out of both sides before the last matching attempt, so a note is not
# thrown away over a dash.
_FOLD = {
    **{ord(c): "-" for c in "‐‑‒–—―−"},
    **{ord(c): "'" for c in "’‘‛`´"},
    **{ord(c): '"' for c in "“”„‟«»"},
    **{ord(c): "" for c in "\u00ad\u200b\u200c\u200d\ufeff"},
    ord("œ"): "oe", ord("Œ"): "Oe", ord("æ"): "ae", ord("Æ"): "Ae",
    ord("ﬁ"): "fi", ord("ﬂ"): "fl", ord("…"): "...",
}


def _fold(value: str) -> tuple[str, list[int]]:
    """Folded text, plus the source offset each folded character came from.

    The offsets are what let a match in the folded text be reported as a span
    in the original: folding is not length-preserving, since œ becomes two
    characters and a soft hyphen becomes none.
    """
    folded: list[str] = []
    offsets: list[int] = []
    for position, char in enumerate(value):
        for replacement in _FOLD.get(ord(char), char):
            folded.append(replacement)
            offsets.append(position)
    return "".join(folded), offsets


@dataclass
class Note:
    """One comment, and where in the text it attaches."""

    anchor: str
    note: str
    number: int = 0  # reading order, 1-based; 0 until located
    start: int = -1
    end: int = -1

    @property
    def located(self) -> bool:
        return self.start >= 0


def parse_notes(raw: str) -> list[Note]:
    """Pull ANCHOR/NOTE blocks out of a model reply, in the order given."""
    notes = []
    for chunk in _BLOCK.split(raw)[1:]:
        anchor, _, rest = chunk.partition("\n")
        marker = _NOTE.search(rest)
        if not marker:
            continue
        body = _BLOCK.split(rest[marker.end() :])[0]
        anchor = anchor.strip().strip(_QUOTES)
        note = " ".join(body.split())
        if anchor and note:
            notes.append(Note(anchor=anchor, note=note))
    return notes


def locate_notes(body: str, notes: list[Note]) -> None:
    """Find each anchor in the body and number the hits in reading order.

    Anchors are numbered by where they land, not by the order the model listed
    them in, so the markers a student sees always ascend down the page. An
    anchor that cannot be found, or that overlaps one already placed, is left
    unlocated.
    """
    folded = _fold(body)
    for note in notes:
        span = _find(body, note.anchor, folded)
        if span:
            note.start, note.end = span

    placed: list[Note] = []
    for note in sorted((n for n in notes if n.located), key=lambda n: n.start):
        if any(note.start < p.end and p.start < note.end for p in placed):
            note.start = note.end = -1  # overlaps an earlier anchor; drop it
            continue
        placed.append(note)
        note.number = len(placed)


def _find(
    body: str, anchor: str, folded: tuple[str, list[int]] | None = None
) -> tuple[int, int] | None:
    """The anchor's span in the body, or None.

    Four attempts, each looser than the last: exactly; allowing any whitespace
    between the words; ignoring case, because a model quoting from mid-sentence
    will re-case the first word; and finally with the typography of both sides
    folded together.
    """
    if not anchor.strip():
        return None  # an all-whitespace anchor would match everywhere, at width 0
    at = body.find(anchor)
    if at != -1:
        return at, at + len(anchor)

    loose = _loose(anchor)
    for flags in (0, re.IGNORECASE):
        match = re.search(loose, body, flags)
        if match:
            return match.span()

    folded_body, offsets = folded or _fold(body)
    folded_anchor, _ = _fold(anchor)
    for flags in (0, re.IGNORECASE):
        match = re.search(_loose(folded_anchor), folded_body, flags)
        if match and match.end() > match.start():
            return offsets[match.start()], offsets[match.end() - 1] + 1
    return None


def _loose(anchor: str) -> str:
    """The anchor as a regex that tolerates any whitespace between its words."""
    return r"\s+".join(re.escape(part) for part in anchor.split())


def body_html(body: str, notes: list[Note] | None = None) -> str:
    """The reading text as HTML paragraphs, with any located anchors marked."""
    spans = sorted((n for n in (notes or []) if n.located), key=lambda n: n.start)
    parts: list[str] = []
    at = 0
    for note in spans:
        parts.append(_prose(body[at : note.start]))
        parts.append(
            f'<span class="anno">{html.escape(body[note.start : note.end])}</span>'
            f'<sup class="anno-num">{note.number}</sup>'
        )
        at = note.end
    parts.append(_prose(body[at:]))
    return re.sub(r"<p>\s*</p>", "", f"<p>{''.join(parts)}</p>")


def _prose(chunk: str) -> str:
    """Escape a stretch of text, turning blank lines into paragraph breaks."""
    escaped = html.escape(chunk)
    escaped = re.sub(r"[ \t]*\n[ \t]*\n\s*", "</p><p>", escaped)
    return re.sub(r"[ \t]*\n[ \t]*", " ", escaped)


def notes_markdown(notes: list[Note]) -> str:
    """The notes as markdown for the working pane, numbered to match the text."""
    located = sorted((n for n in notes if n.located), key=lambda n: n.number)
    lines = [f"**{n.number}.  “{n.anchor}”**  \n{n.note}" for n in located]
    stray = [n for n in notes if not n.located]
    if stray:
        lines.append(
            "---\n*These notes quote something that is not in the text as written, "
            "so they could not be placed. Treat them with suspicion.*"
        )
        lines += [f"*“{n.anchor}”* — {n.note}" for n in stray]
    return "\n\n".join(lines)
