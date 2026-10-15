#!/usr/bin/env python3
"""
modernise_de.py — mechanical layer of pre-1901 German orthography modernisation.

This handles the regular, safe substitutions only. It deliberately does NOT
attempt the judgement calls (compound spelling, comma rules, capitalisation of
nominalised adjectives, ss/ß after long vowels), which need a reader.

    python modernise_de.py in.txt > out.txt
    python modernise_de.py --check in.txt      # list what it would change

Applied in order. Word-boundary anchored so 'Theil' -> 'Teil' does not maul
'Theilnahme' incorrectly (that is handled by its own rule).
"""

from __future__ import annotations

import re
import sys

# ---------------------------------------------------------------------------
# 1. th -> t in native German words (Greek loans keep th: Theorie, Theater...)
# ---------------------------------------------------------------------------
TH_STEMS = [
    ("Theil", "Teil"), ("theil", "teil"),
    ("Thür", "Tür"), ("thür", "tür"),
    ("Thor(?!ax)", "Tor"), ("thor(?!ax)", "tor"),
    ("Thal", "Tal"), ("thal", "tal"),
    ("Thier", "Tier"), ("thier", "tier"),
    ("Thron", "Thron"),          # keeps th
    ("Thun", "Tun"), ("thun", "tun"),
    ("Thätig", "Tätig"), ("thätig", "tätig"),
    ("That", "Tat"), ("that", "tat"),
    ("Muth", "Mut"), ("muth", "mut"),
    ("Werth", "Wert"), ("werth", "wert"),
    ("Rath(?!aus)", "Rat"), ("rath(?!aus)", "rat"),
    ("Noth", "Not"), ("noth", "not"),
    ("Roth(?!aar)", "Rot"), ("roth(?!aar)", "rot"),
    ("Blüthe", "Blüte"), ("blüthe", "blüte"),
    ("Athem", "Atem"), ("athem", "atem"),
    ("Heimath", "Heimat"), ("heimath", "heimat"),
    ("Armuth", "Armut"), ("armuth", "armut"),
    ("Gemüth", "Gemüt"), ("gemüth", "gemüt"),
    ("Wirth", "Wirt"), ("wirth", "wirt"),
]

# ---------------------------------------------------------------------------
# 2. verb and function-word forms
# ---------------------------------------------------------------------------
FORMS = [
    (r"\bgiebt\b", "gibt"),
    (r"\bgiebst\b", "gibst"),
    (r"\bergiebt\b", "ergibt"),
    (r"\bBedürfniß\b", "Bedürfnis"),
    (r"\bVerhältniß\b", "Verhältnis"),
    (r"\bErgebniß\b", "Ergebnis"),
    (r"\bErkenntniß\b", "Erkenntnis"),
    (r"\bZeugniß\b", "Zeugnis"),
    (r"\bGeheimniß\b", "Geheimnis"),
    (r"\bGleichniß\b", "Gleichnis"),
    (r"niß\b", "nis"),           # catch-all for -niß nouns
    (r"nisse\b", "nisse"),
    (r"\bdaß\b", "dass"),
    (r"\bDaß\b", "Dass"),
    (r"\bmuß\b", "muss"),
    (r"\bMuß\b", "Muss"),
    (r"\bgemäß\b", "gemäß"),     # keeps ß (long vowel)
    (r"\bbißchen\b", "bisschen"),
    (r"\bläßt\b", "lässt"),
    (r"\bLäßt\b", "Lässt"),
    (r"\bverläßt\b", "verlässt"),
    (r"\bwißt\b", "wisst"),
    (r"\bmißt\b", "misst"),
    (r"\bmiß", "miss"),          # Mißverständnis -> Missverständnis
    (r"\bMiß", "Miss"),
    (r"\bhäßlich\b", "hässlich"),
    (r"\bnäßt\b", "nässt"),
    (r"\bblaß\b", "blass"),
    (r"\bkraß\b", "krass"),
    (r"\bgewiß\b", "gewiss"),
    (r"\bGewiß", "Gewiss"),
    (r"\bEinfluß\b", "Einfluss"),
    (r"\bSchluß\b", "Schluss"),
    (r"\bGenuß\b", "Genuss"),
    (r"\bFluß\b", "Fluss"),
    (r"\bProzeß\b", "Prozess"),
    (r"\bKongreß\b", "Kongress"),
    (r"\bInteresse\b", "Interesse"),
    (r"\bcivilis", "zivilis"),
    (r"\bCivilis", "Zivilis"),
    (r"\bproduciren\b", "produzieren"),
    (r"(?<![wWhH])iren\b", "ieren"),
    (r"(?<![wWhH])irt\b", "iert"),
    (r"(?<![wWhH])irte\b", "ierte"),
    (r"\bseyn\b", "sein"),
    (r"\bSeyn\b", "Sein"),
    (r"\bhieher\b", "hierher"),
    (r"\bwiederum\b", "wiederum"),
    (r"\bmuß", "muss"),
    (r"\bMuß", "Muss"),
    (r"\bmüß", "müss"),
    (r"\bMüß", "Müss"),
    (r"wußt", "wusst"),
    (r"Wußt", "Wusst"),
    (r"bewußt", "bewusst"),
    (r"Bewußt", "Bewusst"),
    (r"\bfaßt", "fasst"),
    (r"gefaßt", "gefasst"),
    (r"\bHaß\b", "Hass"),
    (r"verhaßt", "verhasst"),
    (r"Kongreß", "Kongress"),
    (r"kongreß", "kongress"),
    (r"Ausschuß", "Ausschuss"),
    (r"Rußland", "Russland"),
    (r"vergeß", "vergess"),
    (r"Vergeß", "Vergess"),
    (r"vergißt", "vergisst"),
    (r"meßlich", "messlich"),
    (r"\bElsaß\b", "Elsass"),
    (r"\bläßt", "lässt"),
    (r"\bpaßt", "passt"),
    (r"\bhaßt", "hasst"),
    (r"\bBaumwollenindustrie\b", "Baumwollindustrie"),
]


def modernise(text: str) -> str:
    for old, new in TH_STEMS:
        text = re.sub(rf"\b{old}", new, text)
    for pat, new in FORMS:
        text = re.sub(pat, new, text)
    return text


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    check = "--check" in sys.argv
    if not args:
        sys.exit(__doc__)

    src = open(args[0], encoding="utf-8").read()
    out = modernise(src)

    if check:
        changed = 0
        for a, b in zip(src.split("\n"), out.split("\n")):
            if a != b:
                changed += 1
                print(f"- {a}\n+ {b}\n")
        print(f"{changed} lines would change", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
