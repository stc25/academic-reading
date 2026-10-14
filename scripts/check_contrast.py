#!/usr/bin/env python3
"""WCAG contrast check for the light and dark theme tokens in tokens.css.

Run from the app root:  python3 scripts/check_contrast.py
Exits non-zero if any pair is below its threshold (4.5 text, 3.0 UI/graphics).
"""
import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "academic_reading_django/reading/static/reading/css/tokens.css"
src = CSS.read_text()


def block(selector):
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", src, re.S)
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", m.group(1)))


light = block(":root")
dark = {**light, **block(':root[data-theme="dark"]')}


def parse(v, tokens):
    v = v.strip()
    m = re.fullmatch(r"var\(--([\w-]+)\)", v)
    if m:
        return parse(tokens[m.group(1)], tokens)
    if v.startswith("#"):
        v = v[1:]
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    m = re.fullmatch(r"rgba?\(([^)]*)\)", v)
    p = [float(x) for x in m.group(1).split(",")]
    return (p[0], p[1], p[2], p[3] if len(p) > 3 else 1.0)


def over(fg, bg):
    a = fg[3]
    return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3)) + (1.0,)


def lum(c):
    def ch(x):
        x /= 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def ratio(fg, bg):
    a, b = lum(over(fg, bg)), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# (foreground, background list, minimum, note)
SURF = ["surface-default", "surface-secondary", "surface-tertiary", "surface-brand"]
PAIRS = [
    ("text-primary", SURF + ["button-secondary-bg", "status-info-light", "status-success-light", "status-warning-light", "status-danger-light"], 4.5),
    ("text-secondary", SURF, 4.5),
    ("text-tertiary", SURF, 4.5),
    ("link-default", ["surface-default", "surface-secondary"], 4.5),
    ("link-hover", SURF, 4.5),
    ("link-active", SURF, 4.5),
    ("text-inverse", ["surface-inverse"], 4.5),
    ("button-primary-text", ["button-primary-bg", "button-primary-hover", "button-primary-active"], 4.5),
    ("status-info-dark", ["status-info-light", "surface-secondary"], 4.5),
    ("status-success-dark", ["status-success-light", "surface-secondary"], 4.5),
    ("status-warning-dark", ["status-warning-light", "surface-secondary"], 4.5),
    ("status-danger-dark", ["status-danger-light", "surface-secondary"], 4.5),
    ("anno", ["surface-secondary"], 4.5),
    ("focus-ring", ["surface-default", "surface-secondary", "surface-brand"], 3.0),
    ("button-secondary-border", ["button-secondary-bg", "surface-default", "surface-secondary"], 3.0),
]
# Fixed colours in app.css for the masthead (dark teal in both themes).
EXTRA = [
    ("masthead nav link (white 85%)", "rgba(255,255,255,0.85)", "surface-inverse", 4.5),
    ("masthead focus ring / switch on", "#92e2e1", "surface-inverse", 3.0),
    ("switch thumb (on) vs track", "#0f2125", "#92e2e1", 3.0),
]

fails = 0
for name, tokens in (("light", light), ("dark", dark)):
    print(f"== {name} ==")
    for fg, bgs, need in PAIRS:
        for bg in bgs:
            r = ratio(parse(f"var(--{fg})", tokens), parse(f"var(--{bg})", tokens))
            bad = r < need
            fails += bad
            if bad:
                print(f"  FAIL {r:5.2f} < {need}  {fg} on {bg}")
    for label, fg, bg, need in EXTRA:
        bgc = parse(f"var(--{bg})", tokens) if not bg.startswith("#") else parse(bg, tokens)
        r = ratio(parse(fg, tokens), bgc)
        if r < need:
            fails += 1
            print(f"  FAIL {r:5.2f} < {need}  {label}")
    print("  (checked)")
print("FAILURES:", fails)
sys.exit(1 if fails else 0)
