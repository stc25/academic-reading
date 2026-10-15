# Auth, groups and managed library — design spec

Date: 2026-10-14. Status: **draft v2 (email workflow added), awaiting review**.
Applies to: `academic-reading/academic-reading` (v1, built first), then
`academic-reading/academic-reading-eng` (v2, ported after v1 is verified).
Reference implementation for SSO: `/var/www/french-chat/frenchbot_django`
(`accounts/social_pipeline.py`, `settings.py` SOCIAL_AUTH_* block).

## 1. Goal

Let Cambridge users sign in with University Microsoft (Entra ID) SSO. Each
signed-in person belongs to one or more **groups**. Each library text is
either open to everyone or restricted to specific groups. Admins manage
users, groups and library texts; teachers have no extra rights and simply
supply texts to admins.

## 2. Confirmed requirements

| # | Requirement | Source |
|---|---|---|
| R1 | Build v1 first, then the same for v2 | user |
| R2 | SSO via Entra ID, **allowlist only** (as french-chat) | user |
| R3 | A person may be in several groups; access = union | user |
| R4 | Apps are live: ship **dormant**, switch over on instruction | user |
| R5 | Entra client ID/secret supplied by user later | user |
| R6 | Admins add/edit library texts and assign them to groups; teachers cannot | user |
| R7 | Email+password login for non-`.cam.ac.uk` users, with account-created/set-password emails as in french-chat: built dormant, switched on later | user |
| R8 | Until groups are created, every text is available to everyone | user |
| R9 | Document the build in a `.md` | user |
| R10 | Admin credentials supplied by user when ready | user |

## 3. Non-goals

- Teacher-facing text upload or group-management UI.
- Enabling email/password login or real email sending (flag and plumbing
  only; SMTP config supplied later).
- Migrating anonymous history to users (it cannot be attributed).
- Changing prompts, activities or LLM behaviour.

## 4. Design

### 4.1 Master switch

`AUTH_REQUIRED` env var, default `false`.

- **false:** behaviour identical to today — anonymous, `session_key`
  identity, library read exactly as now. Migrations and admin still ship.
- **true:** login required for every reading view (except `/health/` and the
  login/SSO routes); history is keyed by user.

Switch-over = set the variable, restart through the shared compose. Rollback
is the same. Nothing in the dormant state may alter any user-visible page.

### 4.2 Users and SSO

- Add `django.contrib.auth`, `contenttypes`, `admin` and `social_django` to
  `INSTALLED_APPS`; add auth middleware and `SocialAuthExceptionMiddleware`.
- Backend: `social_core.backends.azuread_tenant.AzureADTenantOAuth2`, tenant
  ID and env var names (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`) as in
  french-chat. Redirect URI is for this app's own sub-path.
- New app `accounts` containing `AllowedLogin` and the pipeline.
- `AllowedLogin`: `email_or_domain` (exact email or `@domain`), `groups`
  (M2M to `auth.Group`), `matched_user` (nullable FK, set at first login),
  `created_at`. No role field: authority is only `is_staff`/`is_superuser`.
- Pipeline (cf. french-chat): `social_details`, `social_uid`, `auth_allowed`,
  **`enforce_allowlist`** (reject before any user is created),
  `social_user`, `get_username`, `create_user`, `associate_user`,
  `load_extra_data`, `user_details`, **`sync_groups`**.
  - `sync_groups` adds the user to the allowlist entry's groups at every
    login (additive; it never removes groups an admin added manually).
  - Exact-email entries win over domain entries; groups from all matching
    entries are unioned.
- First-login reporting via the existing login-monitor convention, as other
  apps do (`report_login(email, "sso")`) — to be confirmed against
  `/var/www/login-monitor/README.md` during planning.
- Admin accounts are Django superusers created by `createsuperuser` or
  promoted in admin; credentials supplied by the user (R10).

### 4.3 Groups and text access

- Groups: stock `auth.Group`, managed in admin.
- `LibraryText` access: M2M `LibraryText.groups` → `auth.Group`
  (blank allowed).
  - No groups → open to every authenticated user.
  - ≥1 group → visible only to members of at least one of them.
  - Staff/superusers see everything.
- One function `texts_visible_to(user)` is the single source of truth, used
  by the home listing **and** `open_view` (a guessed URL for a hidden text
  returns 404). Uploaded (reader's own) texts are unaffected: private to
  the owner.
- With `AUTH_REQUIRED=false` the visibility filter is bypassed (all texts).

### 4.4 Library moves into the database (R6)

New model `LibraryText` mirroring today's per-text metadata.

- v1 fields: `source_ref` (unique slug, e.g. `de-01`), `title`, `author`,
  `year`, `lang`, `topic`, `register`, `copyright`, `excerpt`, `source`,
  `script`, `body`, `active` (bool), `groups`, timestamps.
- v2 fields: `source_ref`, `title`, `author`, `language`, `level`,
  `source`, `notes`, `body`, `active`, `groups`, timestamps.
- Admin (django-unfold): add/edit by pasting body or uploading a `.txt`/`.md`;
  tick groups; `active` hides a text without deleting it.
- `import_library` management command: idempotent import of the existing
  texts (v1: `texts/manifest.json` + files, 37 texts; v2: `sources/` +
  `source.cfg`). Existing `source_ref`s are preserved so history links keep
  working.
- Library loader reads the DB. File-based reading stays as a fallback behind
  a setting until the import is verified, then is removed in a later change.
  **Ordering matters for the dormant state:** the app must serve an
  identical library before and after deploy, so the import runs as part of
  the deploy and is verified before AUTH_REQUIRED is ever enabled.
- v2 audit task: v2 derives language/script/level at load time from files
  and `source.cfg`; the plan must decide which derived fields are stored vs
  recomputed on save.

### 4.5 History

- `ReadingSession.user` — nullable FK to `AUTH_USER_MODEL`.
- Switch on: sessions/history queries filter by `user`; new rows set `user`.
- Switch off: unchanged `session_key` behaviour.
- Unique constraint becomes per-owner: `(user, source_ref)` when a user is
  set; the `(session_key, source_ref)` constraint remains for anonymous rows.
  Existing anonymous rows are untouched and unreachable once auth is on.

### 4.6 Email/password login (dormant)

`EMAIL_PASSWORD_LOGIN_ENABLED` flag, default false. Non-`.cam.ac.uk` people
cannot use SSO, so when enabled they get the same account workflow as
french-chat (`/var/www/french-chat/django-user-registration-email-workflow.md`,
`accounts/services.py::send_invitation_email`):

- An admin creates the user (and assigns groups) in Django admin. The account
  has an unusable password; a `post_save` signal sends an **account-created
  email after the DB transaction commits**.
- The email contains a short-lived, single-use Django password-reset token
  link to set a password. Passwords are never emailed.
- Login form on the login page (email + password), only for such accounts.
  Non-allowlisted emails cannot register.
- Email delivery config copied from french-chat: `EMAIL_BACKEND` (defaults to
  file-based, so nothing is sent until SMTP is configured), `EMAIL_HOST`,
  `EMAIL_PORT`, `EMAIL_HOST_USER`/`PASSWORD`, `EMAIL_USE_TLS/SSL`,
  `DEFAULT_FROM_EMAIL`. SMTP details to be supplied by the user when this
  is switched on.
- Throttling on login attempts, as french-chat's `_throttled`.

The email plumbing (templates, signal, settings) is built dormant in the
first release alongside the flag; only the switch-on is deferred. The user
model (Django `User`, email-keyed lookup) needs no change.

### 4.7 Deployment

- Dockerfile/requirements: add `social-auth-app-django`, `django-unfold`.
- Env: `AUTH_REQUIRED`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`,
  `EMAIL_PASSWORD_LOGIN_ENABLED`, the `EMAIL_*` / `DEFAULT_FROM_EMAIL` settings
  (4.6; file-based backend until SMTP is supplied), plus whatever SSO callback host settings
  french-chat uses behind Caddy.
- Rebuild/restart via the shared `/var/www/cnlp-docker-hosting` compose
  only (v1 and v2 are separate services/databases there).
- Session cookie name/path already app-specific; keep.
- Admin site mounted at an app-specific path (as french-chat's
  `/django-admin/`) so it does not collide with other apps behind Caddy.

## 5. Testing

- Unit: `texts_visible_to` (no groups, one group, several groups, staff,
  inactive); allowlist matching (exact, domain, union, no match → reject);
  `sync_groups` additive; history scoping with flag on/off.
- Regression: with `AUTH_REQUIRED=false` the existing views return what they
  returned before (home, open, activity, history).
- Import: running `import_library` twice is a no-op; counts match (v1: 37).
- Email workflow (dormant plumbing, tested with the file-based backend):
  admin-created user triggers one account-created email after commit; the
  link sets a password once and then expires; non-allowlisted email cannot
  register; login throttling works; flag off = login form absent.
- Manual (needs Entra credentials, after R5): real SSO round trip, rejected
  non-allowlisted account, group-restricted text hidden/visible.

## 6. Rollout order

1. Build and test v1 with flag off; deploy dormant; verify library identical.
2. Port to v2; deploy dormant; verify.
3. On user's instruction: load Entra credentials (and, when email/password
   login is wanted, SMTP details and `EMAIL_PASSWORD_LOGIN_ENABLED=true`), create allowlist entries
   and groups, receive admin login, set `AUTH_REQUIRED=true` (v1 and v2
   independently).

## 7. Risks

- **Library migration** is the riskiest step (breaks reading if import is
  wrong) — mitigated by file fallback and identical-before/after check.
- **Unique-constraint change** on `ReadingSession` needs a careful migration
  on live MariaDB data.
- **Anonymous history orphaned** at switch-over — accepted; to be stated to
  users.
- v2's derived fields may complicate the DB model (see 4.4 audit task).

## 8. Open items (non-blocking)

- Login-monitor integration details (confirm in planning).
- Whether anonymous browsing of the library should remain possible after
  switch-over (current assumption: no, login required).
