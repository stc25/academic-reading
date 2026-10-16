# Sign-in (SSO and email accounts)

Both apps (`academic-reading` v1 and `academic-reading-eng` v2) require sign-in **on the `auth` branch**
(the live `cnlp` apps run `main` and stay anonymous). There is no on/off switch any more: signed-out visitors
are sent to the sign-in page, history belongs to the signed-in account, and the library is shown according to
the reader's groups (see "Groups and texts" below).

## What it adds

| Piece | Where | Notes |
|---|---|---|
| University Microsoft (Entra ID) SSO | `accounts/pipeline.py`, `settings.py` | allowlist only: an account not on the allowlist is rejected before any user is created |
| Email + password accounts | `accounts/views.py`, `services.py`, `admin.py` | for people outside `cam.ac.uk`; admin-created, the person sets their own password from an emailed single-use link; passwords are never emailed |
| Allowlist | `AllowedLogin` model, admin | an exact email, a bare CRSid (Cambridge addresses only), or a whole `@domain` |
| Auth gate | `accounts/middleware.py` | always on: anonymous visitors are redirected to the login page (health check, static files, admin and auth URLs stay open). If no sign-in method is configured at all, a plain "sign-in is not set up" page (HTTP 503) is shown instead of a dead-end login page |
| Per-user history | `ReadingSession.user` | with sign-in on, history and uploaded texts belong to the account and follow it across devices |
| Admin site | `/django-admin/` | users, groups and the allowlist (django-unfold theme) |
| Login throttling | `accounts/throttle.py` | 10 attempts per email and 30 per IP per 15 minutes (per process) |

Cambridge addresses cannot use the password form (they must use SSO). Inactive accounts cannot sign in
either way. `?next=` redirects only follow same-host URLs.

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `LIBRARY_SOURCE` | `db` | `db` = library from the admin (group-aware); `files` = the bundled files, every text ungrouped (emergency fallback) |
| `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` | empty | Entra app registration. The Microsoft button is hidden until both are set |
| `AZURE_TENANT_ID` | University of Cambridge tenant | only change for a different tenant |
| `EMAIL_PASSWORD_LOGIN_ENABLED` | `false` | shows the email/password form and sends account-created emails |
| `EMAIL_BACKEND` | file-based | writes emails to `sent_emails/` instead of sending. Set `django.core.mail.backends.smtp.EmailBackend` and the `EMAIL_*` values to really send |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL` | see file | SMTP delivery |
| `MONITOR_URL`, `MONITOR_TOKEN`, `MONITOR_APP_NAME` | empty | optional login reporting; does nothing unless all three are set |

## Switch-over runbook

1. **Deploy.** *Take a database backup first* (`deploy/backup-db.sh`). Pull, then `docker compose up -d --build`. The
   entrypoint runs migrations and, on first start only, `import_library --if-empty` to load the bundled texts into the
   database. Check with `docker compose exec <app> python manage.py import_library --check` (v1: 37 texts, v2: 8).
2. **Create the first admin** in each app container:
   `docker compose exec academic-reading python manage.py createsuperuser` and
   `docker compose exec academic-reading-eng python manage.py createsuperuser` (each prompts for a username,
   email and password; one per app, since each has its own database). Admin is at `https://<hostname>/academic-reading/django-admin/` and
   `.../academic-reading-eng/django-admin/`.
3. **Register the Entra apps** (one registration per app, type *Web*) with these redirect URIs, then put the
   client ID and secret in each app's `.env`:
   - `https://<hostname>/academic-reading/auth/sso/complete/azuread-tenant-oauth2/`
   - `https://<hostname>/academic-reading-eng/auth/sso/complete/azuread-tenant-oauth2/`
4. **Add allowlist entries** in each admin (Accounts → Allowed logins). Examples: `abc123`,
   `abc123@cam.ac.uk`, `@ling.cam.ac.uk`.
5. **Email accounts (optional):** configure SMTP, set `EMAIL_PASSWORD_LOGIN_ENABLED=true`, then add users in
   admin (Authentication → Users → Add). They get a set-password email. The action *Send set-password email*
   re-sends it.
6. **Smoke test:** an anonymous visit redirects to the login page; an allowlisted account signs in and sees the library;
   a non-allowlisted one is refused with a message.

**Rollback:** there is no switch to restore anonymous access. Set `LIBRARY_SOURCE=files` to serve the bundled files
(every text ungrouped) or revert the release; data is untouched.

## Groups and texts

Groups limit which signed-in readers can open which library text. Everything is managed in the Django admin
(`/academic-reading/django-admin/`, `/academic-reading-eng/django-admin/`).

**The rule** (`reading/access.py`, evaluated on every request, so changes apply on the person's next page load):

1. Signed out: no texts.
2. Staff, superusers, and members of any group with **Sees every text** ticked (e.g. *Technical*): every active text.
3. Everyone else: active texts with **no groups**, plus active texts limited to one of their groups. A person in
   several groups gets the union. A text no one can see returns 404 even at a guessed URL, and drops out of their history.

**Set it up**
- **Create groups:** Authentication and Authorization -> Groups -> Add. Tick **Sees every text** on the group's page for
  groups like *Technical*.
- **Add people already signed in:** Users -> pick the person -> Groups.
- **Add people before they have signed in:** Accounts -> Allowed logins -> pick (or add) the entry (an email, a CRSid or
  `@domain`) -> Groups. Saving the entry also adds any accounts that **already exist** and match it, straight away (the page
  says how many). People with no account yet get the groups at their first Microsoft sign-in, and every sign-in adds the
  groups of all matching entries again. It only ever adds: nobody is removed from a group automatically. The list's
  action **Add existing matching accounts to these entries' groups now** re-applies entries in bulk.
- **Add a text:** Reading -> Library texts -> Add. Paste the body, or upload a `.txt`/`.md` file (the language is detected
  if left blank). Tick the groups that may read it; leave them empty for everyone signed in.
- **Assign many texts at once:** in the Library texts list, filter (e.g. by language), select, then choose **Add selected
  texts to a group...** or **Remove selected texts from a group...**. Other actions: Activate / Deactivate (hide a text
  without deleting it).
- Deactivate rather than delete the bundled texts: `import_library` only loads into an empty library, so deleted texts
  do not come back, but history links to a deleted text stop working.

**Import command** (`python manage.py import_library`): creates missing texts and leaves existing ones alone;
`--if-empty` (used by the entrypoint) does nothing once the library has texts; `--update` refreshes content fields of
existing texts (never groups or active); `--check` compares the database with the files and fails on any difference.

## Things to know

- **Anonymous history is not carried over.** It can't be attributed to a person, so earlier
  anonymous history is unreachable (the rows stay in the database).
- **Sign-in begins with a POST.** Current `social-auth-app-django` only accepts POST to start SSO, so the
  login page uses a form button. Linking straight to `.../auth/sso/login/azuread-tenant-oauth2/` returns 405.
- **Django 5.2.** `requirements.txt` moved from Django 5.0/5.1 to 5.2 (LTS), which current `django-unfold`
  needs. The existing test suite passes unchanged on it.
- **Behind the proxy.** `SECURE_PROXY_SSL_HEADER` trusts `X-Forwarded-Proto`, so the SSO redirect URI and emailed
  links are `https`. The reverse proxy must send that header (Caddy does by default; add
  `proxy_set_header X-Forwarded-Proto $scheme;` in nginx). Cookies are `Secure` unless `DJANGO_DEBUG=true`.
- **Email outbox.** The default file backend writes inside the container (`/app/sent_emails`), which is lost on
  rebuild. Use SMTP for real use.
- **MariaDB and the per-user unique constraint.** `ReadingSession` has a conditional unique constraint on
  (user, source_ref); MariaDB cannot enforce conditional constraints, so Django skips it there (a `models.W036`
  warning). The views still use `get_or_create` per user, so duplicates do not occur in normal use.
- **Throttle** is per gunicorn worker process, so the effective limit is a small multiple of the stated one.
- **Not verifiable without credentials:** a real Microsoft round trip. The tests check that the SSO start URL
  points at the University tenant with the right redirect URI, that the allowlist runs before any user is
  created, and the pipeline steps; the full round trip needs the Entra client ID and secret.

## Tests

From either app's `academic_reading_django/` directory (SQLite is used when `DATABASE_URL` is empty):

```bash
DATABASE_URL= PUBLIC_PATH= FORCE_SCRIPT_NAME= STATIC_URL=/static/ python manage.py test accounts reading
```

v1: 133 tests, v2: 135. They cover allowlist matching, the pipeline and group syncing at login, login/logout/throttle/redirect
safety, set-password link single use, admin invite and resend, the always-on gate (and the 503 page), per-user history
isolation, the SSO start URL, the who-sees-what matrix, hidden-text 404s on every route, `import_library`, and the
library admin (paste/upload, bulk actions). Run inside the container image they also include one SSO test
(`test_redirect_uri_is_https_behind_the_proxy`) that fails there with the installed `social-auth-core` 6.x; it is
unrelated to groups.
