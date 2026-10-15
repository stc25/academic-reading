"""Languages: names, codes, script questions, and detection.

Version 1 knew four languages and hard-coded them. This one accepts any
language a text might be in, so the code is only ever a label — for display,
for routing a model in config.yaml, and for looking up an optional block of
language-specific advice in prompts.yaml. Nothing breaks when a language is
absent from the table below; it simply passes through under whatever name the
text was filed with, and falls back to the default model.
"""

from __future__ import annotations

import re
import unicodedata

import hanzidentifier
from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

DetectorFactory.seed = 0

# ISO 639 code -> English name. The 55 langdetect can identify, plus the
# historical and less-common languages an academic reader is likely to meet,
# which it cannot. Detection is only ever a suggestion the reader can correct,
# and source.cfg states the language outright, so a gap here costs nothing.
NAMES = {
    "af": "Afrikaans", "ang": "Old English", "ar": "Arabic", "az": "Azerbaijani",
    "be": "Belarusian", "bg": "Bulgarian", "bn": "Bengali", "bs": "Bosnian",
    "ca": "Catalan", "cs": "Czech", "cy": "Welsh", "da": "Danish",
    "de": "German", "el": "Greek", "en": "English", "eo": "Esperanto",
    "es": "Spanish", "et": "Estonian", "eu": "Basque", "fa": "Persian",
    "fi": "Finnish", "fr": "French", "ga": "Irish", "gd": "Scottish Gaelic",
    "gl": "Galician", "grc": "Ancient Greek", "gu": "Gujarati", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "hy": "Armenian",
    "id": "Indonesian", "is": "Icelandic", "it": "Italian", "ja": "Japanese",
    "ka": "Georgian", "kk": "Kazakh", "kn": "Kannada", "ko": "Korean",
    "la": "Latin", "lt": "Lithuanian", "lv": "Latvian", "mk": "Macedonian",
    "ml": "Malayalam", "mr": "Marathi", "ms": "Malay", "ne": "Nepali",
    "nl": "Dutch", "no": "Norwegian", "pa": "Punjabi", "pl": "Polish",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sa": "Sanskrit",
    "sk": "Slovak", "sl": "Slovenian", "so": "Somali", "sq": "Albanian",
    "sr": "Serbian", "sv": "Swedish", "sw": "Swahili", "ta": "Tamil",
    "te": "Telugu", "th": "Thai", "tl": "Tagalog", "tr": "Turkish",
    "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese", "zh": "Chinese",
}

_BY_NAME = {name.casefold(): code for code, name in NAMES.items()}

# Endonyms and the spellings people actually type.
_ALIASES = {
    "deutsch": "de", "français": "fr", "francais": "fr", "italiano": "it",
    "español": "es", "espanol": "es", "castellano": "es", "português": "pt",
    "portugues": "pt", "nederlands": "nl", "русский": "ru", "ελληνικά": "el",
    "中文": "zh", "汉语": "zh", "漢語": "zh", "日本語": "ja", "한국어": "ko",
    "mandarin": "zh", "modern greek": "el", "classical greek": "grc",
    "koine": "grc", "koine greek": "grc", "old greek": "grc",
    "classical chinese": "zh", "literary chinese": "zh",
    "brazilian portuguese": "pt", "castilian": "es", "farsi": "fa",
    "hebrew (modern)": "he", "norwegian bokmål": "no", "bokmal": "no",
    "serbo-croatian": "sr", "flemish": "nl", "anglo-saxon": "ang",
}

# langdetect's own codes, mapped onto ours.
_FROM_LANGDETECT = {"zh-cn": "zh", "zh-tw": "zh"}

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힯ᄀ-ᇿ]")


def resolve(value: str) -> tuple[str, str]:
    """Turn whatever a source.cfg or a reader gave us into (code, name).

    A language the table does not know keeps its own text as both code and
    name, so it still displays properly and can still be routed in config.yaml.
    """
    raw = (value or "").strip()
    if not raw:
        return "", ""
    key = raw.casefold()
    code = key if key in NAMES else _BY_NAME.get(key) or _ALIASES.get(key)
    if code:
        return code, NAMES[code]
    return key, raw


def name_of(code: str) -> str:
    return NAMES.get(code, code)


def detect(body: str) -> tuple[str, float]:
    """Best guess at the language of a text, as (code, confidence).

    The CJK block is decided by script rather than by langdetect, which is
    unreliable on classical Chinese and cannot tell Chinese from Japanese in a
    passage light on kana.
    """
    letters = [ch for ch in body if ch.isalpha()]
    if letters:
        han = len(_CJK.findall(body))
        if han / len(letters) > 0.2:
            if _KANA.search(body):
                return "ja", 1.0
            if _HANGUL.search(body):
                return "ko", 1.0
            return "zh", 1.0
    if _HANGUL.search(body):
        return "ko", 1.0
    try:
        ranked = detect_langs(body)
    except LangDetectException:
        return "", 0.0
    if not ranked:
        return "", 0.0
    best = max(ranked, key=lambda c: c.prob)
    return _FROM_LANGDETECT.get(best.lang, best.lang), float(best.prob)


def script_of(body: str) -> str:
    """'traditional', 'simplified', 'mixed' or '' — Chinese and Japanese only."""
    return {
        hanzidentifier.TRADITIONAL: "traditional",
        hanzidentifier.SIMPLIFIED: "simplified",
        hanzidentifier.BOTH: "simplified",
        hanzidentifier.MIXED: "mixed",
    }.get(hanzidentifier.identify(body), "")


def counts_characters(code: str) -> bool:
    """Languages whose reading load is better measured in characters."""
    return code in {"zh", "ja", "ko", "th"}


def is_latin_script(body: str, sample: int = 4000) -> bool:
    """Whether the text is written mostly in the Latin alphabet.

    Decides whether a vocabulary table needs a romanisation column: telling a
    reader that 之 is pronounced zhī is essential, and telling them that
    Gesellschaft is pronounced Gesellschaft is not.
    """
    latin = other = 0
    for ch in body[:sample]:
        if not ch.isalpha():
            continue
        if "LATIN" in unicodedata.name(ch, ""):
            latin += 1
        else:
            other += 1
    return latin >= other
