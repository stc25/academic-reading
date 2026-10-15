# Academic Reading (v1)

A reading-skills tutor for learners of **German, French, Italian and Chinese**.
Pick an authentic academic or literary text, then work through ten guided activities
before, during and after reading it. The tutor is an LLM (Ollama Cloud) that is
prompted per activity; sign-in is optional and off by default (see below).

Live path: `/academic-reading/`. Sibling app: [`academic-reading-eng`](../academic-reading-eng/)
(v2, any language, English throughout).

## What the learner can do

**Choose a text**
- Browse a bundled library of **37 public-domain texts** (11 German, 10 Italian, 8 French,
  8 Chinese), each with author, year, topic, length and a source link. The list is in
  `texts/manifest.json`.
- Search the library by title, author, topic or language, and filter by language.
- **Upload their own** `.txt` or `.md` file. The language is detected automatically (and can be
  chosen by hand if detection fails); Markdown is reduced to plain prose. Uploaded texts are
  private to that reader's session.

**Choose how the tutor talks to them**
- **Level, chosen by the reader:** Post-Beginner (A2/B1), Intermediate (B2) or Advanced (C1).
  It changes how much the tutor explains and how it words things.
- **Reply language, per activity:** English or the language of the text. Each activity has a
  sensible default (see below) that the reader can switch.

**Ten activities**, shown as a menu beside the text:

| # | Activity | What happens | Reply default |
|---|---|---|---|
| 1 | Pre-reading | vocabulary, structure and background, without giving the content away | English |
| 2 | Summative comprehension | questions on the whole text; the reader answers and gets feedback | text language |
| 3 | Detailed comprehension | questions on specific details; reader answers, gets feedback | text language |
| 4 | Passive summary | a concise summary pitched at the reader's level | text language |
| 5 | Active summary | the reader writes a summary; the tutor comments on its accuracy | text language |
| 6 | Notes | the reader writes bullet-point notes; the tutor comments | text language |
| 7 | Structure | how the text is built, narrative or argumentative, and its rhetorical means | English |
| 8 | Stylistic observation | style, genre conventions, contrast with typical English writing | English |
| 9 | Close commentary | commentary **anchored inside the text itself** at the relevant passages | English |
| 10 | Post-reading take-aways | the key language points to carry to the next text | English |

**Everything else**
- Two-column layout: the text on one side, the working pane on the other. Replies stream in as
  they are written.
- **History** page listing every text the reader has worked on, with the activities tried and attempt counts; **Reset**
  clears one text's history.
- Light and dark theme (follows the OS, remembered per browser).
- **Anonymous by default:** a browser cookie (`arm_sessionid`, one year) keeps a reader's work between visits.
- **Optional sign-in (off by default):** with `AUTH_REQUIRED=true` readers must sign in with University Microsoft
  (Entra ID) SSO, restricted to an admin-managed allowlist, or with an admin-created email + password account for
  people outside Cambridge. History then belongs to the account and follows it across devices. Admin site at
  `/django-admin/`. Setup and switch-over runbook: [`docs/LOGIN.md`](../docs/LOGIN.md).

## Behaviour worth knowing

- **Shared reply cache.** The first reader to generate an activity's opening reply for a text,
  level and reply language triggers the model; everyone after gets the stored reply instantly.
  Feedback on a reader's own writing, and uploaded texts, are never cached. Details: `docs/REPLY_CACHE.md`
  in the deployment repo. Clear it with `python manage.py clear_reply_cache --all` (or `--activity`, `--text`).
- **One opening result per reader** per activity/level/reply-language: the Generate button is
  hidden once they have one. Changing level or reply language, or pressing Reset, makes it
  available again.
- **Models** (`config.yaml`): `gemma4:31b` for German, French and Italian; `gpt-oss:120b` for Chinese
  (it gets classical-Chinese pinyin right where gemma4 does not). Temperature 0.3.
- Replies depend on the LLM, so wording varies between runs; the structure and substance are stable.

## Configuration files

| File | Controls |
|---|---|
| `config.yaml` | models per language, levels, the ten activities (default reply language, interactive or not, spoiler rules, button labels), reading-pane sizes |
| `prompts.yaml` | every prompt, per activity and per level |
| `texts/` | the bundled library: `<lang>/<id>.txt` plus `manifest.json` |

These files are baked into the Docker image, so **rebuild after editing** them.

## Running it

Production / server: see the deployment README at the repository root (Docker Compose,
MariaDB, reverse proxy). In short, from the repo root:

```bash
docker compose up -d --build academic-reading
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
  texts/              bundled library
  config.yaml  prompts.yaml
  Dockerfile  docker/entrypoint.sh   (migrate, collectstatic, gunicorn)
app.py  lib/  uv.lock                the original Streamlit prototype, not used by Docker
```
