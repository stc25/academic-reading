# Academic Reading (v2)

A reading-skills tutor for academic texts in **any language**. Everything the app says is in
**English**, whatever the text is written in. The reader picks a text and works through ten
guided activities; the tutor is an LLM (Ollama Cloud) prompted per activity. Readers must sign in (see below).

Live path: `/academic-reading-eng/`. Sibling app: [`academic-reading`](../academic-reading/)
(v1, four languages, level and reply language chosen by the reader).

## How this differs from v1

| | v1 | v2 (this app) |
|---|---|---|
| Languages | German, French, Italian, Chinese | any |
| App's own language | English or the target language, per activity | English throughout |
| Reader's level | chosen by the reader | not asked; the **text** carries a level |
| Texts | 37 bundled, `manifest.json` | whatever is in `sources/`, described by `source.cfg` |
| Model routing | one model per language | a default plus per-language exceptions |
| Formats | `.txt` | `.txt`, `.md` |

The ten activities and the two-column layout are the same.

## What the reader can do

**Choose a text**
- Browse the library, grouped by language, with title, author, level and a source link.
  Search by title, author, topic or language, and filter by language.
- **Upload their own** `.txt` or `.md` file (private to their session). The language is detected,
  or the reader can type it (e.g. "German"); uploads use the default level.
- Texts outside 400–2000 words (times 1.6 for languages written without spaces) still open, with
  a warning: too short and the activities have little to work with, too long and the end falls out
  of the model's context.

**Ten activities**, all answered in English:

| # | Activity | What happens |
|---|---|---|
| 1 | Pre-reading | vocabulary, structure and background, without giving the content away |
| 2 | Summative comprehension | questions on the whole text; the reader answers and gets feedback |
| 3 | Detailed comprehension | questions on specific details; reader answers, gets feedback |
| 4 | Passive summary | a concise summary of the text in English |
| 5 | Active summary | the reader writes a summary; the tutor comments on its accuracy |
| 6 | Notes | the reader writes bullet-point notes; the tutor comments |
| 7 | Structure | how the text is built, narrative or argumentative, and its rhetorical means |
| 8 | Stylistic observation | style, genre conventions, contrast with typical English writing |
| 9 | Close commentary | commentary **anchored inside the text itself** at the relevant passages |
| 10 | Post-reading take-aways | the key language points to carry to the next text |

**Everything else**
- Two-column layout, with replies streaming in as they are written.
- **History** page of every text worked on, with activities tried and attempt counts; **Reset** clears one text's history.
- Light and dark theme (follows the OS, remembered per browser).
- **Sign-in is mandatory (auth branch):** readers sign in with University Microsoft (Entra ID) SSO, restricted to an
  admin-managed allowlist, or with an admin-created email + password account for people outside Cambridge. History
  belongs to the account and follows it across devices. The library lives in the admin: each text can be limited to
  groups, and a group can be marked "sees every text". Admin site at `/django-admin/`. Setup, groups and runbook: [`docs/LOGIN.md`](../docs/LOGIN.md).

## Behaviour worth knowing

- **The level belongs to the text**, read as *the level of reader this text is meant for*:
  introductory texts are explained generously, advanced ones sparingly. If you would rather it meant
  "this text is hard, so help more", swap the `introductory` and `advanced` blocks under
  `level_guidance` in `prompts.yaml`; nothing in the code depends on the direction.
- **Shared reply cache.** The first reader to generate an activity's opening reply for a text
  triggers the model; everyone after gets the stored reply instantly. Feedback on a reader's own
  writing, and uploaded texts, are never cached. Clear with
  `python manage.py clear_reply_cache --all` (or `--activity`, `--text`).
- **One opening result per reader** per activity: the Generate button is hidden once they have one;
  Reset makes it available again.
- **Language detection is only a suggestion.** `langdetect` covers 55 languages and does not include
  Latin, Ancient Greek or Old English, so it will confidently mislabel them; state the language in
  `source.cfg`. Chinese, Japanese and Korean are decided by script rather than by langdetect.
- Markdown is reduced to plain prose at load (headings lose their `#`, links keep their text, code
  fences are dropped). It is not rendered, because close commentary anchors notes at character
  offsets in the body, so what the reader sees must be exactly the string the model was given.

## Adding texts

Drop `.txt` or `.md` files into `sources/`. That is enough: a file with no catalogue entry is still
offered, titled from its filename with its language guessed. Describe it in `source.cfg` to do better:

```ini
[marx]
title    = Manifest der Kommunistischen Partei — I. Bourgeois und Proletarier
author   = Karl Marx & Friedrich Engels, 1848
language = German
file     = marx-manifest.txt
level    = advanced
source   = https://www.marxists.org/deutsch/...
notes    = Opening of section I. Orthography modernised.
```

One section per text; the section name is the id and is never shown. Every field is optional:

| field | what it does |
|---|---|
| `title` | what the reader sees; defaults to the filename |
| `author` | who wrote it, with the date if known (`Jules Ferry, 1885`). Shown as a byline and passed to the model as provenance. There is no separate year field. Leave it out rather than guess; the model is forbidden from inventing an author. `by` also works |
| `language` | English name or ISO code; detected if absent. `lang` also works |
| `file` | the file in `sources/`; defaults to `<section>.txt` |
| `level` | `introductory`, `intermediate`, `advanced`, or a CEFR band (A1 to C2). Defaults to `default_level` in `config.yaml` |
| `source` | provenance, shown under the text. `url` also works |
| `notes` | one line on what this passage is |

A named file that is missing is reported, not fatal. Currently shipped: 8 sample texts in German,
French, Italian, Chinese and Portuguese (one deliberately uncatalogued, to exercise the fallback).

## Configuration files

| File | Controls |
|---|---|
| `config.yaml` | models (a `default` plus `by_language` exceptions; keys are ISO codes or English names), levels and their aliases, text length limits, the ten activities, reading-pane sizes |
| `prompts.yaml` | every prompt. An activity declares which turns it has by which templates it defines (`user`, `brief`, `feedback`); any other key becomes a `${placeholder}`, resolved per level if it is a mapping |
| `source.cfg`, `sources/` | the text library |

Models today: `gemma4:31b` by default; `gpt-oss:120b` for Chinese, Japanese, Korean, Latin and Ancient
Greek. A language named nowhere gets the default, so adding a text in a new language needs no change.

These files are baked into the Docker image, so **rebuild after editing** them.

## Running it

Production / server: see the deployment README at the repository root. In short, from the repo root:

```bash
docker compose up -d --build academic-reading-eng
```

Local development (SQLite is used when `DATABASE_URL` is not set):

```bash
cd academic_reading_django
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export OLLAMA_API_KEY=...          # from ollama.com
python manage.py migrate
python manage.py runserver
python manage.py test              # reply-cache tests
```

## Layout

```
academic_reading_django/
  accounts/           sign-in: allowlist model, SSO pipeline, login views, auth gate, admin
  reading/            views, models (ReadingSession, ActivityTurn, CachedReply), templates, static
  reading/logic/      prompts, LLM client, corpus loading, annotations
  sources/  source.cfg   the text library
  config.yaml  prompts.yaml
  Dockerfile  docker/entrypoint.sh   (migrate, collectstatic, gunicorn)
app.py  lib/  uv.lock                the original Streamlit prototype, not used by Docker
```
