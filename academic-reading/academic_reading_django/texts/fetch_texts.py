#!/usr/bin/env python3
"""
fetch_texts.py — download the Academic-Reading starter corpus.

Run this on a machine with internet access:

    pip install requests beautifulsoup4
    python fetch_texts.py

It reads sources.json and writes one plain-text file per source into
texts/<lang>/_raw/<id>.txt, then prints a report of what succeeded,
what needs a manual check, and what is marked FD (in copyright) and so
must be supplied by you.

These are FULL texts, not excerpts. Trimming each to a coherent ~1000-word
passage is the next step — the excerpt_note field in sources.json says
which passage to take for each one.

Nothing here is destructive: existing files are skipped unless you pass
--force.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run:  pip install requests beautifulsoup4")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dependency. Run:  pip install requests beautifulsoup4")


ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources.json"
UA = {
    "User-Agent": "Academic-Reading-corpus-builder/1.0 (educational use; contact: cz201@cam.ac.uk)"
}
TIMEOUT = 30
PAUSE = 1.0  # be polite to the servers


# --------------------------------------------------------------------------
# text extraction
# --------------------------------------------------------------------------

def html_to_text(html: str) -> str:
    """Strip an HTML page down to readable body text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(
        ["script", "style", "nav", "header", "footer", "noscript", "form", "aside"]
    ):
        tag.decompose()

    # Wikisource / MediaWiki: the article body is the useful part
    body = soup.select_one("#mw-content-text") or soup.body or soup
    text = body.get_text("\n")
    return tidy(text)


def wikitext_to_text(wikitext: str) -> str:
    """Crude but serviceable wikitext -> plain text."""
    t = wikitext
    t = re.sub(r"<ref[^>]*?/>", "", t)
    t = re.sub(r"<ref.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)          # simple templates
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)          # nested, one more pass
    t = re.sub(r"\{\|.*?\|\}", "", t, flags=re.S)  # tables
    t = re.sub(r"\[\[(?:File|Image|Datei|Fichier|Immagine|File):[^\]]*\]\]", "", t)
    t = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", t)  # piped links
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)           # plain links
    t = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", t)
    t = re.sub(r"</?[a-zA-Z][^>]*>", "", t)             # stray html
    t = re.sub(r"^[=]{2,}\s*(.*?)\s*[=]{2,}\s*$", r"\1", t, flags=re.M)
    t = re.sub(r"'''?", "", t)
    return tidy(t)


def tidy(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    out, blank = [], False
    for ln in lines:
        if not ln:
            blank = True
            continue
        if blank and out:
            out.append("")
        blank = False
        out.append(ln)
    return "\n".join(out).strip() + "\n"


# --------------------------------------------------------------------------
# resolvers
# --------------------------------------------------------------------------

def get(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text


def fetch_url(url: str) -> tuple[str, str]:
    return html_to_text(get(url)), url


def fetch_wikisource(wiki: str, title: str) -> tuple[str, str]:
    """Fetch raw wikitext for a known page title."""
    api = f"https://{wiki}.wikisource.org/w/index.php"
    url = f"{api}?title={requests.utils.quote(title, safe='')}&action=raw"
    return wikitext_to_text(get(url)), (
        f"https://{wiki}.wikisource.org/wiki/{requests.utils.quote(title, safe='')}"
    )


def search_wikisource(wiki: str, query: str) -> tuple[str, str]:
    """Search Wikisource, take the best hit, fetch it.

    Used where the exact page title is uncertain. The resolved title is
    printed so you can sanity-check it.
    """
    api = f"https://{wiki}.wikisource.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 5,
        "format": "json",
        "srnamespace": 0,
    }
    r = requests.get(api, params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    hits = r.json().get("query", {}).get("search", [])
    if not hits:
        raise LookupError(f"no Wikisource hit for {query!r} on {wiki}.wikisource")
    title = hits[0]["title"]
    text, url = fetch_wikisource(wiki, title)
    return text, f"{url}   [resolved from search: {title!r}]"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download existing files")
    ap.add_argument("--only", help="comma-separated ids or langs, e.g. de,fr or de-01")
    args = ap.parse_args()

    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    entries = data["texts"]

    if args.only:
        wanted = {w.strip() for w in args.only.split(",")}
        entries = [e for e in entries if e["id"] in wanted or e["lang"] in wanted]

    ok, manual, failed, skipped = [], [], [], []

    for e in entries:
        eid, lang = e["id"], e["lang"]
        outdir = ROOT / lang / "_raw"
        outdir.mkdir(parents=True, exist_ok=True)
        outfile = outdir / f"{eid}.txt"
        res = e["resolve"]

        if res["type"] == "manual":
            manual.append(e)
            placeholder = outdir / f"{eid}.NEEDS-MANUAL-COPY.md"
            if not placeholder.exists() or args.force:
                placeholder.write_text(
                    f"# {eid} — {e['author']}, {e['title']} ({e['year']})\n\n"
                    f"**In copyright (FD).** Not downloaded automatically.\n\n"
                    f"Paste a ~1000-word excerpt into `{eid}.txt` in this folder.\n\n"
                    f"Passage to take: {e.get('excerpt_note', '—')}\n",
                    encoding="utf-8",
                )
            continue

        if outfile.exists() and not args.force:
            skipped.append(e)
            continue

        try:
            if res["type"] == "url":
                text, src = fetch_url(res["url"])
            elif res["type"] == "wikisource":
                text, src = fetch_wikisource(res["wiki"], res["title"])
            elif res["type"] == "wikisource_search":
                text, src = search_wikisource(res["wiki"], res["query"])
            else:
                raise ValueError(f"unknown resolve type {res['type']!r}")

            words = len(text.split()) if lang != "zh" else len(text)
            if words < 200:
                raise ValueError(f"suspiciously short result ({words} units)")

            header = (
                f"# {e['author']} — {e['title']} ({e['year']})\n"
                f"# source: {src}\n"
                f"# copyright: {e['copyright']}\n"
                f"# NOTE: full text. Excerpt to take: {e.get('excerpt_note', '—')}\n\n"
            )
            outfile.write_text(header + text, encoding="utf-8")
            ok.append((e, words, src))
            print(f"  ok    {eid}  {words:>7} units  {src[:80]}")

        except Exception as exc:  # noqa: BLE001 — we want to keep going
            failed.append((e, exc))
            print(f"  FAIL  {eid}  {exc}")
            if e.get("fallback_url"):
                print(f"        try by hand: {e['fallback_url']}")

        time.sleep(PAUSE)

    print("\n" + "=" * 70)
    print(f"downloaded : {len(ok)}")
    print(f"skipped    : {len(skipped)} (already present; use --force to redo)")
    print(f"manual (FD): {len(manual)}")
    print(f"failed     : {len(failed)}")
    if failed:
        print("\nFailed — resolve these by hand:")
        for e, exc in failed:
            print(f"  {e['id']}  {e['author']}, {e['title']}")
            print(f"      {exc}")
            if e.get("fallback_url"):
                print(f"      fallback: {e['fallback_url']}")
    if manual:
        print("\nIn copyright — paste your own excerpt into <id>.txt:")
        for e in manual:
            print(f"  {e['id']}  {e['author']}, {e['title']} ({e['year']})")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
