"""The text corpus: the bundled library, uploads, and language detection."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import hanzidentifier
from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

from .settings import TEXTS_DIR

DetectorFactory.seed = 0

LANG_NAMES = {"de": "German", "fr": "French", "it": "Italian", "zh": "Chinese"}
SUPPORTED = tuple(LANG_NAMES)

UPLOAD_SUFFIXES = (".txt", ".md", ".markdown")

_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
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
    """Normalise an uploaded file to the plain prose the reading pane shows.

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

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


@dataclass
class Text:
    """One reading text, from the library or uploaded by the student."""

    id: str
    lang: str
    title: str
    body: str
    author: str = ""
    year: int | None = None
    topic: str = ""
    copyright: str = ""
    excerpt: str = ""
    source: str = ""
    script: str = ""
    register: str = ""
    uploaded: bool = False
    detection: dict = field(default_factory=dict)

    @property
    def language_name(self) -> str:
        return LANG_NAMES.get(self.lang, self.lang)

    @property
    def is_cjk(self) -> bool:
        return self.lang == "zh"

    @property
    def length(self) -> int:
        return count_length(self.body, self.lang)

    @property
    def length_unit(self) -> str:
        return "characters" if self.is_cjk else "words"

    @property
    def byline(self) -> str:
        bits = [b for b in (self.author, str(self.year) if self.year else "") if b]
        return " · ".join(bits)


def count_length(body: str, lang: str) -> int:
    if lang == "zh":
        return len(_CJK.findall(body))
    return len(body.split())


def script_of(body: str) -> str:
    """'traditional', 'simplified', 'mixed' or '' for Chinese text."""
    result = hanzidentifier.identify(body)
    return {
        hanzidentifier.TRADITIONAL: "traditional",
        hanzidentifier.SIMPLIFIED: "simplified",
        hanzidentifier.BOTH: "simplified",
        hanzidentifier.MIXED: "mixed",
    }.get(result, "")


def detect_language(body: str) -> tuple[str | None, float]:
    """Best guess at the language of a text, as (code, confidence).

    CJK is decided by character ratio — langdetect is unreliable on classical
    Chinese — and everything else goes to langdetect restricted to our set.
    """
    stripped = "".join(ch for ch in body if not ch.isspace())
    if stripped and len(_CJK.findall(body)) / len(stripped) > 0.2:
        return "zh", 1.0
    try:
        ranked = [c for c in detect_langs(body) if c.lang in SUPPORTED]
    except LangDetectException:
        return None, 0.0
    if not ranked:
        return None, 0.0
    best = max(ranked, key=lambda c: c.prob)
    return best.lang, float(best.prob)


def load_library(texts_dir: Path = TEXTS_DIR) -> tuple[dict, list[Text]]:
    """Read manifest.json and every text it lists."""
    manifest_path = texts_dir / "manifest.json"
    with manifest_path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)

    texts: list[Text] = []
    for entry in manifest.get("texts", []):
        body = (texts_dir / entry["file"]).read_text(encoding="utf-8").strip()
        texts.append(
            Text(
                id=entry["id"],
                lang=entry["lang"],
                title=entry["title"],
                body=body,
                author=entry.get("author", ""),
                year=entry.get("year"),
                topic=entry.get("topic", ""),
                copyright=entry.get("copyright", ""),
                excerpt=entry.get("excerpt", ""),
                source=entry.get("source", ""),
                script=entry.get("script", ""),
                register=entry.get("register", ""),
            )
        )
    return manifest, texts


def text_from_upload(name: str, raw: bytes) -> Text:
    """Build a Text from an uploaded .txt/.md/.markdown file, detecting its language."""
    try:
        raw_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = raw.decode("utf-8", errors="replace")
    is_markdown = Path(name).suffix.lower() in (".md", ".markdown")
    body = plain_text(raw_text, is_markdown)

    lang, confidence = detect_language(body)
    return Text(
        id=f"upload:{name}",
        lang=lang or "",
        title=Path(name).stem,
        body=body,
        uploaded=True,
        script=script_of(body) if lang == "zh" else "",
        detection={"language": lang, "confidence": confidence},
    )
