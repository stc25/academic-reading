"""The text corpus: whatever is in sources/, plus what the reader uploads.

There is no bundled library in this version. Texts are dropped into sources/ as
.txt or .md and described in source.cfg. The catalogue is advisory: a file with
no entry still appears, titled from its filename and with its language guessed,
because a reader who has just copied a file in should not have to edit a config
before they can read it.
"""

from __future__ import annotations

import configparser
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .languages import (
    counts_characters,
    detect,
    is_latin_script,
    name_of,
    resolve,
    script_of,
)
from .settings import ROOT, Config

SUFFIXES = (".txt", ".md", ".markdown")

# source.cfg keys, and the spellings that mean the same thing.
FIELDS = {
    "title": ("title",),
    "author": ("author", "by", "writer"),
    "language": ("language", "lang"),
    "file": ("file", "file-name", "file_name", "filename"),
    "level": ("level",),
    "source": ("source", "url"),
    "notes": ("notes", "note", "excerpt"),
}

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


@dataclass
class Text:
    """One reading text, from sources/ or uploaded by the reader."""

    id: str
    lang: str
    title: str
    body: str
    author: str = ""
    language: str = ""
    level_value: str = ""
    source: str = ""
    notes: str = ""
    file: str = ""
    uploaded: bool = False
    detected: bool = False
    confidence: float = 0.0
    script: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def language_name(self) -> str:
        return self.language or name_of(self.lang) or "unknown"

    @property
    def counts_characters(self) -> bool:
        return counts_characters(self.lang)

    @property
    def length(self) -> int:
        return count_length(self.body, self.lang)

    @property
    def length_unit(self) -> str:
        return "characters" if self.counts_characters else "words"

    @property
    def needs_romanisation(self) -> bool:
        return not is_latin_script(self.body)

    @property
    def is_cjk(self) -> bool:
        return self.lang in {"zh", "ja", "ko"}


def count_length(body: str, lang: str) -> int:
    if counts_characters(lang):
        return len(_CJK.findall(body)) or len(
            [ch for ch in body if ch.isalpha() or _CJK.match(ch)]
        )
    return len(body.split())


# --------------------------------------------------------------------------- #
# Reading files
# --------------------------------------------------------------------------- #
_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
# Horizontal whitespace only, never \s: a newline inside one of these patterns
# would swallow the blank line before it and weld two paragraphs together.
_MD_STRIP = (
    (re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.M), ""),   # ATX headings
    (re.compile(r"^[ \t]{0,3}#{1,6}[ \t]*$", re.M), ""),  # empty heading
    (re.compile(r"^[ \t]{0,3}>[ \t]?", re.M), ""),        # block quotes
    (re.compile(r"^[ \t]{0,3}([-*_])[ \t]*(\1[ \t]*){2,}$", re.M), ""),  # rules
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),           # images
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),       # links keep their text
    (re.compile(r"(\*\*|__)(.+?)\1", re.S), r"\2"),      # bold
    (re.compile(r"(?<!\w)([*_])(?!\s)(.+?)(?<!\s)\1(?!\w)", re.S), r"\2"),  # italic
    (re.compile(r"`([^`]+)`"), r"\1"),                   # inline code
)


def plain_text(raw: str, is_markdown: bool) -> str:
    """Normalise a file to the plain prose the reading pane shows.

    Markdown is reduced rather than rendered. The pane builds its own HTML so
    that close commentary can anchor notes at character offsets in the body,
    and that only works if what the reader sees and what the model was given
    are the same string.
    """
    body = unicodedata.normalize("NFC", raw.replace("\r\n", "\n").replace("\r", "\n"))
    if is_markdown:
        body = _FENCE.sub("", body)
        for pattern, replacement in _MD_STRIP:
            body = pattern.sub(replacement, body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def read_text_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return plain_text(raw, path.suffix.lower() in (".md", ".markdown"))


# --------------------------------------------------------------------------- #
# source.cfg
# --------------------------------------------------------------------------- #
def load_catalogue(path: Path) -> dict[str, dict]:
    """Read source.cfg into {section: {field: value}}.

    Every section is one text. Field names are matched loosely, so FILE-NAME,
    file_name and file all work, and unknown fields are ignored rather than
    refused.
    """
    if not path.exists():
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # keep the case we were given; we fold it ourselves
    parser.read(path, encoding="utf-8")

    catalogue: dict[str, dict] = {}
    for section in parser.sections():
        raw = {k.strip().casefold(): (v or "").strip() for k, v in parser[section].items()}
        entry = {}
        for canonical, spellings in FIELDS.items():
            for spelling in spellings:
                if raw.get(spelling):
                    entry[canonical] = raw[spelling]
                    break
        catalogue[section.strip()] = entry
    return catalogue


# --------------------------------------------------------------------------- #
# Building the library
# --------------------------------------------------------------------------- #
def corpus_signature(config: Config) -> tuple:
    """A cheap fingerprint of the sources directory and the catalogue.

    Passed to the app's cache as an argument so that dropping a text into
    sources/, editing one, or editing source.cfg refreshes the library on the
    next rerun instead of needing Streamlit restarted.
    """
    settings = config.texts
    directory = ROOT / settings.get("directory", "sources")
    catalogue = ROOT / settings.get("catalogue", "source.cfg")

    parts: list[tuple] = []
    if catalogue.exists():
        parts.append(("", catalogue.stat().st_mtime_ns, 0))
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in SUFFIXES:
                stat = path.stat()
                parts.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(parts)


def load_library(config: Config) -> tuple[list[Text], list[str]]:
    """Every readable text in the sources directory, and any problems found."""
    settings = config.texts
    directory = ROOT / settings.get("directory", "sources")
    catalogue = load_catalogue(ROOT / settings.get("catalogue", "source.cfg"))

    problems: list[str] = []
    if not directory.is_dir():
        return [], [f"No `{directory.name}/` directory — create it and put texts in it."]

    files = {
        path.name: path
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() in SUFFIXES
    }

    texts: list[Text] = []
    claimed: set[str] = set()

    for section, entry in catalogue.items():
        filename = entry.get("file") or f"{section}.txt"
        path = files.get(filename)
        if path is None:
            problems.append(
                f"`source.cfg` [{section}] names `{filename}`, which is not in "
                f"`{directory.name}/`."
            )
            continue
        claimed.add(filename)
        texts.append(_build(section, path, entry, config))

    # Files nobody catalogued still get read; the catalogue is a convenience.
    for filename, path in files.items():
        if filename in claimed:
            continue
        texts.append(_build(Path(filename).stem, path, {}, config))

    texts.sort(key=lambda t: (t.language_name, t.title.casefold()))
    return texts, problems


def _build(text_id: str, path: Path, entry: dict, config: Config) -> Text:
    body = read_text_file(path)
    stated = entry.get("language", "")
    code, name = resolve(stated)
    detected = False
    confidence = 0.0
    if not code:
        code, confidence = detect(body)
        name = name_of(code)
        detected = True

    text = Text(
        id=text_id,
        lang=code,
        language=name,
        title=entry.get("title") or path.stem.replace("_", " "),
        body=body,
        author=entry.get("author", ""),
        level_value=entry.get("level", ""),
        source=entry.get("source", ""),
        notes=entry.get("notes", ""),
        file=path.name,
        detected=detected,
        confidence=confidence,
        script=script_of(body) if code in {"zh", "ja"} else "",
    )
    text.warnings = length_warnings(text, config)
    return text


def length_warnings(text: Text, config: Config) -> list[str]:
    """Whether the text falls outside the configured length range."""
    settings = config.texts
    low = settings.get("min_words", 400)
    high = settings.get("max_words", 2000)
    if text.counts_characters:
        ratio = settings.get("character_ratio", 1.6)
        low, high = round(low * ratio), round(high * ratio)

    unit = text.length_unit
    if text.length < low:
        return [f"Short: {text.length} {unit}, below the {low} the activities expect."]
    if text.length > high:
        return [f"Long: {text.length} {unit}, above {high} — the model may lose the end."]
    return []


def text_from_upload(name: str, raw: bytes, config: Config) -> Text:
    """Build a Text from an uploaded file, detecting its language."""
    body = plain_text(
        raw.decode("utf-8", errors="replace"),
        Path(name).suffix.lower() in (".md", ".markdown"),
    )
    code, confidence = detect(body)
    text = Text(
        id=f"upload:{name}",
        lang=code,
        language=name_of(code),
        title=Path(name).stem.replace("_", " "),
        body=body,
        file=name,
        uploaded=True,
        detected=True,
        confidence=confidence,
        script=script_of(body) if code in {"zh", "ja"} else "",
    )
    text.warnings = length_warnings(text, config)
    return text
