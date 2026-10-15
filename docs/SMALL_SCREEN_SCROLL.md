# Keep the reader in the work area on small screens

Built 2026-10-14 in both apps. **Status: deployed to both live apps 2026-10-14.** Live check in headless Chromium at 390×844 against production (cached texts, no LLM calls): activity link lands exactly on the activity list in both apps; Generate+reload lands just above it with the list in view (slightly off because of the wide-result overflow noted below); test sessions deleted.

## Problem
Below 1024px the page is one column: the whole reading text (~8,000px tall on a phone), then the
activity list and work pane. Clicking an activity, changing level/reply language, or Generate /
"Check my answers" (which end with `window.location.reload()`) loaded the page at the top, back in
the text. `preventDefault` can't fix this — the links must navigate — so instead the page being
left remembers, and the page being arrived at scrolls back.

## Fix
`reading/static/reading/js/keep-position.js` (loaded by `read.html` before `generate.js`):
- On narrow screens (`max-width: 1023px`) a click on `.activity-nav a`, a `change` in
  `.level-reply-row`, or `generate.js` (via `window.keepWorkInView()`, called before both
  reload sites incl. the 409 "already generated" reload) sets a `sessionStorage` flag.
- On arrival the flag is read and cleared; if set, `history.scrollRestoration = "manual"` and
  `.activity-nav` is scrolled to the top of the viewport (immediately and again on `load`).
- Wide screens, plain visits and a blocked/unavailable `sessionStorage` behave as before.

## Verification (headless Chromium, 390×844 and 1280×900, local copies of both apps)
| | script blocked | script on |
|---|---|---|
| activity link (phone) | scrollY 0 — the bug | lands on the activity list |
| change level (phone) | 0 | lands on the activity list |
| Generate → reload (phone) | browser-dependent | lands on / just above the list |
| any of these (desktop) | no forced scroll | no forced scroll |
| plain revisit afterwards | 0 | 0 (flag cleared) |
Plus a unit test per app that the page loads the script before `generate.js` (18 tests each).

## The wide-result overflow (found while testing; fixed and deployed 2026-10-14; one follow-up rule pending deploy)
**Cause:** markdown tables in generated results (the vocabulary tables — "As it appears / Dictionary
form / English gloss / Note" — in pre-reading, passive summary and take-aways) have a minimum width of
400–600px. In the one-column layout the grid track is `1fr` (= `minmax(auto, 1fr)`), so it grew to the
table's width, and the mobile browser then widened/zoomed the whole page. 9 of 32 seeded pages
overflowed at 390px (all three take-aways pages, pre-reading, passive summary…). A second, rarer cause:
the long German title word "Kommunistischen" is wider than a 320px phone allows.

**Fix** (CSS only, `app.css`, inside the existing `@media (max-width: 1023px)` block, both apps):
`.pageview` column `minmax(0, 1fr)`, `.pageview > * { min-width: 0 }`, `.model-output { overflow-x: auto }`
(wide tables scroll inside their box), `.pageview h1 { overflow-wrap: anywhere }`.
Desktop CSS is byte-identical to production (verified by diff) — a first attempt applied it at all
widths and clipped the table on desktop, so it was narrowed to the single-column breakpoint.

**Verified** (headless Chromium, 32 pages = 4 texts × 8 activities of real model output):
horizontal overflow 9/32 → 0/32 at 320, 360, 390, 768, 1023 and 1280px; desktop table fully visible;
after Generate the phone lands exactly on the activity list (previously slightly above it).
**Follow-up found on the live eng app at 320px:** the eng-only line "Source: https://www.marxists.org/…" (`p.draft-meta`) is an unbreakable URL 80px wider than the screen; added `.draft-meta { overflow-wrap: anywhere }` to the same narrow-screen block in both apps. Locally: 0 overflow for all 8 eng texts at 320/360/390px. **Built and tested; not yet deployed.**

Trade-off: on a phone a wide table is clipped with no visible hint that it scrolls sideways.

## Testing note
Headless Chromium needed libs unavailable without root; they were unpacked from `.deb` files into
the session scratchpad and used via `LD_LIBRARY_PATH` (nothing installed system-wide).
