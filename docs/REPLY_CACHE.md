# Shared reply cache — build log

Built 2026-10-14 in both apps: `academic-reading` (v1) and `academic-reading-eng` (v2).
**Status: deployed to both live apps 2026-10-14.**

## What it does

The first time anyone opens a library text and generates an activity's *opening* reply,
the model is called and the reply is stored. Every later reader of that text/activity/level
gets the stored reply instantly, with no LLM call. Cacheable activities (those with an
opening turn): pre-reading, summative comprehension (questions), detailed comprehension
(questions), passive summary, structure, stylistic observation, close commentary,
post-reading take-aways.

Never cached: feedback turns (they depend on what the learner wrote), activities 5 and 6
(feedback only), **uploaded texts**, errors, empty replies.

## Why caching is safe — the experiment

`docs/experiments/reply-variance/` (script, raw results, `summary.txt`): 4 texts (de/fr/it/zh)
× 8 activities × 3 runs = 96 real calls at Intermediate level. Wording differs between runs
(word overlap 0.35–0.55) but headings, number of questions, length (CV 2–14%) and substance
are stable; zero failures. Chinese (`gpt-oss:120b`) varies most. Conclusion: any one stored
variant is as good as any other.

## Design

- Table `CachedReply` (MariaDB; JSON files were rejected — two gunicorn workers would race).
- `key` = SHA-256 of `[model, system message, user message, sampling options]`. The messages
  embed the text body, level, reply language, metadata and prompts, so editing a text,
  `prompts.yaml` or `config.yaml` misses the cache automatically — nothing to invalidate.
- `hits` counts reuse; `source_ref`/`activity_id`/`level_id`/`reply_language` are for
  inspection and selective clearing.
- Concurrent first requests both call the model; the first to finish wins (`store()` ignores
  the duplicate-key race).
- A cache hit still writes an `ActivityTurn` so the reader's own history looks identical, and
  returns plain text, which the existing front-end JS reads and then reloads — no JS change.
- **One result per reader (changed 2026-10-14, after the first deploy):** once a reader has a
  stored opening for an activity (v1: per activity + level + reply language; v2: per activity),
  the Generate / "Generate questions" button is not shown and `generate_view` answers 409
  ("You already have a result…"; the JS reloads the page to show it). So there is **no
  Regenerate** any more. The comprehension answer box is unaffected. **Reset** still clears a
  text's history; generating again afterwards is free because the shared cache serves the
  stored reply. Changing level/reply language in v1 is a different combination, so Generate
  reappears for it.
- v2 differences: level comes from the text/session and replies are always English, so
  `reply_language` is stored blank.

## Clearing

No admin site exists in either app yet (it arrives with the auth build), so:

```bash
docker exec cnlp-academic-reading python manage.py clear_reply_cache --all
docker exec cnlp-academic-reading python manage.py clear_reply_cache --activity structure
docker exec cnlp-academic-reading python manage.py clear_reply_cache --text de-01
# eng: container cnlp-academic-reading-eng
```
Use after a model upgrade you want applied, or to drop a bad reply. When the Django admin is
added by the auth plan, register `CachedReply` there with a delete action.

## Files

Per app (`academic_reading_django/`): `reading/models.py` (`CachedReply`),
`reading/views.py` (`generate_view`, `_stream_and_save`), `reading/migrations/0002_cachedreply.py`,
`reading/management/commands/clear_reply_cache.py`, `reading/tests/test_reply_cache.py` (13 tests).

## Testing

```bash
cd <app>/academic_reading_django
DATABASE_URL= PUBLIC_PATH= FORCE_SCRIPT_NAME= STATIC_URL=/static/ ../.django-venv/bin/python manage.py test reading
```
(The overrides stop `.env` pointing tests at MariaDB and at the production URL prefix; `STATIC_URL` must not be empty.) 17 tests per app.

## Deploying (done 2026-10-14)

Adds one table via migration `0002`; no existing data touched. Rebuild only through the shared
compose (`/var/www/cnlp-docker-hosting`), v1 service `academic-reading`, v2 `academic-reading-eng`.
Back up each DB first. After deploy: generate an activity on a library text twice from two
browsers and confirm the second is instant and `docker exec … manage.py shell -c
"from reading.models import CachedReply as C; print(C.objects.count(), sum(C.objects.values_list('hits', flat=True)))"`
shows hits.

### Deployment record (2026-10-14)

- Pre-deploy DB dumps: `docs/backups/academic_reading_v1-20261014-152041.sql` and
  `academic_reading_eng-20261014-152041.sql` (dir is mode 700; contains reader history).
- `docker compose build/up -d --no-deps academic-reading academic-reading-eng` from
  `/var/www/cnlp-docker-hosting`; both healthy; `0002_cachedreply` applied in each.
- Live check (two cookie-separate readers, same library text/activity): v1 de-01 pre_reading
  4.5s then 0.09s; eng marx pre_reading 6.7s then 0.09s, byte-identical replies. The test
  sessions were deleted; the two resulting cache rows (one per app, 1 hit each) were kept.

### Follow-up: remove Regenerate (2026-10-14)

Built and tested in both apps (17 tests each, mutation-checked); **deployed live 2026-10-14** (no migration; rebuilt via the shared compose, both healthy). Live check on cached texts, no LLM calls: button present before generating; first generate 200 in ~0.09s (served from cache); afterwards button count 0, no "Regenerate" text, result shown; second generate 409 in ~0.08s. Test sessions deleted.
