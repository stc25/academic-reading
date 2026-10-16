# Groups and database library — design spec

Date: 2026-10-16. Status: **draft, awaiting review**.
Applies to the **`auth` branch only** (combined repo `stc25/academic-reading`). The live `cnlp` apps run `main`,
stay anonymous and are not touched. Build v1 (`academic-reading`) first, then v2 (`academic-reading-eng`).

Builds on `2026-10-14-auth-and-groups-design.md`. **It supersedes that spec's sections 4.1 (master switch),
4.3 (groups and text access) and 4.4 (library) and the "Non-goals" line about teachers.** Everything else in the
2026-10-14 spec (SSO, allowlist, email accounts, history) stands and is already built.

## 1. Goal

Restrict which signed-in people can read which library texts, by group. Examples that must work:

- Group **Technical** sees every text.
- Group **Arabic** sees only Arabic texts (plus ungrouped texts, see 4.1).
- Signed-out visitors see no texts.

Admins manage users, groups and library texts in the Django admin. Teachers have no special rights.

## 2. Confirmed requirements

| # | Requirement | Source |
|---|---|---|
| G1 | Signed-out visitors see **no** texts; texts exist only after sign-in | user 2026-10-16 |
| G2 | A text with no group ticked is visible to **every signed-in user** | user 2026-10-16 |
| G3 | Library moves into the database; admins add/edit texts and tick groups | user 2026-10-16 |
| G4 | A group can be marked "sees every text" (Technical) | user 2026-10-16 |
| G5 | Users already signed in, and people who have not yet signed in, can both be put into groups | user 2026-10-16 |
| G6 | Branch only; live `main` unchanged | user 2026-10-16 |
| G7 | Person may be in several groups; access is the union | 2026-10-14 R3 |

## 3. Non-goals

Teacher-facing upload or group UI; per-person (not per-group) text access; migrating anonymous history;
changing prompts, activities or LLM behaviour; keeping an anonymous browsing mode on this branch.

## 4. Design

### 4.1 Access rule — one function

`reading/access.py::texts_visible_to(user)` (v1 and v2 each have their own copy of the module, same logic) returns
the visible `LibraryText` queryset. It is the only place the rule lives.

1. Anonymous user -> **none**.
2. `is_staff` or `is_superuser` -> all active texts.
3. User in any group whose `GroupAccess.sees_all_texts` is true -> all active texts.
4. Otherwise -> active texts that have **no groups**, plus active texts that have **at least one of the user's groups**.

Inactive texts are never visible to readers (admins still see them in the admin). Access is evaluated on every
request, so adding or removing a group takes effect on the person's next page load; no sign-out is needed.

Used by every view that touches a library text: home listing, `open_view`, `read_redirect_view`, `activity_view`,
`generate_view`, `submit_view`, and the history listing.

- A hidden or missing text returns **404**, including for guessed URLs.
- A history entry for a library text the person can no longer see is not listed and cannot be opened. Their
  uploaded texts are unaffected: private to the owner, as now.
- Anonymous requests are stopped earlier by the auth gate (4.2), so they never reach this rule.

### 4.2 Sign-in is mandatory (anonymous mode retired on this branch)

- `AUTH_REQUIRED` stops being a switch: the gate is always on. Anonymous visitors are redirected to
  `accounts:login` (health, static, admin and `/auth/` stay open). The env var is removed from settings and
  `.env.production.example`; a leftover value in a `.env` is ignored.
- If **no** sign-in method is configured (no Microsoft keys and email login off), the gate shows a plain
  "sign-in is not set up" page (HTTP 503) instead of redirecting to a dead-end login page.
- `ReadingSession.user` is always set for new rows. Old rows with only a `session_key` remain in the database,
  unreachable, as already documented. The unique constraint becomes `(user, source_ref)`; the legacy
  `(session_key, source_ref)` constraint stays for old rows.
- The "front door" redirect in `home_view` (commit `5e4a5c8`) becomes redundant and is removed.
- Tests pinning anonymous behaviour (`test_baseline`, `DormantGateTests`) are rewritten around signed-in-only.
  `docs/LOGIN.md` is updated: no "ships off / dormant" language.

### 4.3 Groups, users and the allowlist

- Groups are Django's `auth.Group`, managed in admin (already registered with the unfold theme).
- New model `accounts.GroupAccess`: `group` (OneToOne, `related_name="access"`), `sees_all_texts` (bool, default
  false). Shown as an inline on the Group admin page. A group with no `GroupAccess` row behaves as false.
- **Already signed in:** an admin edits the person's groups on the User admin page (stock field).
- **Not yet signed in:** `AllowedLogin` gains `groups` (M2M to `auth.Group`, blank). A new pipeline step
  `sync_groups`, after `finish_login`, adds the user to the groups of **every** matching allowlist entry at
  **every** login. It is additive only and never removes a group an admin set by hand. Exact-email, CRSid and
  `@domain` entries all contribute (union).
- **Email-password accounts** (non-Cambridge): groups are set on the User admin page when the admin creates them.

### 4.4 The library in the database

New model `reading.LibraryText`, one per app (fields mirror today's per-text metadata):

- **v1:** `source_ref` (unique slug, e.g. `de-01`), `title`, `author`, `year`, `lang`, `topic`, `register`,
  `copyright`, `excerpt`, `source`, `script`, `body`, `active`, `groups`, `created_at`, `updated_at`.
- **v2:** `source_ref` (unique slug), `title`, `author`, `language_code`, `language_name`, `level_id`, `source`,
  `notes`, `script`, `body`, `active`, `groups`, `created_at`, `updated_at`. `language_*` and `script` are
  detected from the body on save when left blank and then **stored**; `level_id` defaults to the config's
  `default_level`.
- `groups`: `ManyToManyField(auth.Group, blank=True)`.

Existing `ReadingSession.source_ref` values for library texts (`lib:<id>`) map to `LibraryText.source_ref = <id>`,
so every existing history link keeps working. Uploaded texts are not in `LibraryText`.

`reading/logic/corpus.py::load_library` reads `LibraryText` and returns the same `Text` objects it does today,
so views, prompts and templates do not change. A setting `LIBRARY_SOURCE` (`db` or `files`) keeps the file
loader as a fallback; `files` mode treats every text as ungrouped. Default `db` once the import is verified.

### 4.5 Import

`python manage.py import_library` loads the current library, **idempotently** (update-or-create by `source_ref`,
never touching `groups` or `active` on a re-run):

- v1: `texts/manifest.json` + the files it names (37 texts: de 11, fr 8, it 10, zh 8).
- v2: `sources/` + `source.cfg` (8 texts), through the existing `load_library` so derived fields match.

It prints counts, and `--check` compares the database library with the file library field by field and exits
non-zero on any difference. **Deploy order:** migrate -> import -> `--check` passes -> only then run with
`LIBRARY_SOURCE=db`.

### 4.6 Admin

- `LibraryTextAdmin` (unfold): list shows title, language, author, groups, active; filters by language, group,
  active; search by title/author/`source_ref`. Add a text by pasting the body or uploading `.txt`/`.md`
  (reusing `plain_text`/`text_from_upload`, so the stored body is what readers and the model see).
- Bulk actions: **Add to group...**, **Remove from group...** (intermediate page to pick the group) and
  **Activate / Deactivate**. "All Arabic texts -> Arabic group" = filter by language, select all, add to group.
- `GroupAdmin`: the `GroupAccess` inline, plus a read-only count of texts and users per group.
- Only staff can reach the admin; teachers get no extra rights.

## 5. Testing

Both apps. Django `TestCase`, SQLite, run as in `docs/LOGIN.md`.

- **Visibility matrix** (`texts_visible_to`): anonymous; signed in with no group; one group; two groups (union);
  Technical (`sees_all_texts`); staff; superuser; inactive text; ungrouped text; text grouped to another group.
- **Views:** hidden text returns 404 on open/read/activity/generate/submit; hidden text not in home or history;
  group added mid-session takes effect on the next request; person removed from a group loses the text.
- **Gate:** anonymous redirected to login on every route; `503` page when no sign-in method is configured.
- **Pipeline:** `sync_groups` adds groups from exact, CRSid and domain entries, is additive, and is idempotent.
- **Import:** produces the expected counts (37 / 8), is idempotent, preserves `source_ref`, does not reset groups
  or `active`; `--check` passes after import and fails after a deliberate edit.
- **Admin:** upload-or-paste creates a text; each bulk action changes only the selected texts.
- **Regression:** existing accounts/reading tests still pass except those rewritten in 4.2, and the one known
  failing test (`test_redirect_uri_is_https_behind_the_proxy`) is unchanged by this work.

## 6. Rollout

1. Build on a branch off `auth`, v1 first, then v2; commit per logical step; docs in `docs/AUTH_AND_GROUPS.md` and
   `docs/LOGIN.md`.
2. Deploy to lcapps from `auth`: migrate -> `import_library` -> `--check` -> set `LIBRARY_SOURCE=db`.
3. Everything starts ungrouped, so signed-in users see the same library as before.
4. Admin creates groups (Technical with `sees_all_texts`; Arabic, etc.), assigns texts, and adds people or
   allowlist entries to groups.

## 7. Open items

- The real list of groups (names, who is in each) is supplied by the user when ready.
- Neither app has Arabic texts today; they must be supplied (and added through the new admin) before the Arabic
  group has anything to restrict.
- Rolling back: there is no variable to restore anonymous access. Fallbacks are `LIBRARY_SOURCE=files` and
  reverting the release.
