# Sign-in (SSO and email accounts)

Both apps (`academic-reading` v1 and `academic-reading-eng` v2) can require sign-in.
**It ships switched off.** With `AUTH_REQUIRED` unset or `false` the apps behave exactly as before:
anonymous readers, history kept per browser. Nothing changes for readers until you switch it on.

This covers *login only*. Group-restricted texts and a database-managed library are not part of this
work (see `docs/AUTH_AND_GROUPS.md` for that plan).

## What it adds

| Piece | Where | Notes |
|---|---|---|
| University Microsoft (Entra ID) SSO | `accounts/pipeline.py`, `settings.py` | allowlist only: an account not on the allowlist is rejected before any user is created |
| Email + password accounts | `accounts/views.py`, `services.py`, `admin.py` | for people outside `cam.ac.uk`; admin-created, the person sets their own password from an emailed single-use link; passwords are never emailed |
| Allowlist | `AllowedLogin` model, admin | an exact email, a bare CRSid (Cambridge addresses only), or a whole `@domain` |
| Auth gate | `accounts/middleware.py` | with `AUTH_REQUIRED=true`, anonymous visitors are redirected to the login page (health check, static files, admin and auth URLs stay open) |
| Per-user history | `ReadingSession.user` | with sign-in on, history and uploaded texts belong to the account and follow it across devices |
| Admin site | `/django-admin/` | users, groups and the allowlist (django-unfold theme) |
| Login throttling | `accounts/throttle.py` | 10 attempts per email and 30 per IP per 15 minutes (per process) |

Cambridge addresses cannot use the password form (they must use SSO). Inactive accounts cannot sign in
either way. `?next=` redirects only follow same-host URLs.

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `AUTH_REQUIRED` | `false` | master switch. `true` = sign-in required, history per account |
| `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` | empty | Entra app registration. The Microsoft button is hidden until both are set |
| `AZURE_TENANT_ID` | University of Cambridge tenant | only change for a different tenant |
| `EMAIL_PASSWORD_LOGIN_ENABLED` | `false` | shows the email/password form and sends account-created emails |
| `EMAIL_BACKEND` | file-based | writes emails to `sent_emails/` instead of sending. Set `django.core.mail.backends.smtp.EmailBackend` and the `EMAIL_*` values to really send |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL` | see file | SMTP delivery |
| `MONITOR_URL`, `MONITOR_TOKEN`, `MONITOR_APP_NAME` | empty | optional login reporting; does nothing unless all three are set |

## Switch-over runbook

1. **Deploy this code with the flags off.** Pull, then `docker compose up -d --build`. The entrypoint runs
   migrations (adds the auth, admin, social-auth and `AllowedLogin` tables, and a nullable `user` column on
   `ReadingSession`). Check the apps still work anonymously. *Take a database backup first* (`deploy/backup-db.sh`).
2. **Create the first admin** in each app container:
   `docker compose exec academic-reading python manage.py createsuperuser` (and the same for
   `academic-reading-eng`). Admin is at `https://<hostname>/academic-reading/django-admin/` and
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
6. **Switch on:** set `AUTH_REQUIRED=true`, `docker compose up -d` (the container is recreated with the new
   `.env`). Smoke test: anonymous visit redirects to the login page; an allowlisted account signs in; a
   non-allowlisted one is refused with a message.

**Rollback:** set `AUTH_REQUIRED=false` and recreate the container. Data is untouched.

## Things to know

- **Anonymous history is not carried over.** It can't be attributed to a person, so once sign-in is on,
  earlier anonymous history is unreachable (the rows stay in the database).
- **Sign-in begins with a POST.** Current `social-auth-app-django` only accepts POST to start SSO, so the
  login page uses a form button. Linking straight to `.../auth/sso/login/azuread-tenant-oauth2/` returns 405.
- **Django 5.2.** `requirements.txt` moved from Django 5.0/5.1 to 5.2 (LTS), which current `django-unfold`
  needs. The existing test suite passes unchanged on it.
- **Behind the proxy.** `SECURE_PROXY_SSL_HEADER` trusts `X-Forwarded-Proto`, so the SSO redirect URI and emailed
  links are `https`. The reverse proxy must send that header (Caddy does by default; add
  `proxy_set_header X-Forwarded-Proto $scheme;` in nginx). Cookies are `Secure` unless `DJANGO_DEBUG=true`.
- **Email outbox.** The default file backend writes inside the container (`/app/sent_emails`), which is lost on
  rebuild. That is fine while dormant; use SMTP for real use.
- **Throttle** is per gunicorn worker process, so the effective limit is a small multiple of the stated one.
- **Not verifiable without credentials:** a real Microsoft round trip. The tests check that the SSO start URL
  points at the University tenant with the right redirect URI, that the allowlist runs before any user is
  created, and the pipeline steps; the full round trip needs the Entra client ID and secret.

## Tests

From either app's `academic_reading_django/` directory (SQLite is used when `DATABASE_URL` is empty):

```bash
DATABASE_URL= PUBLIC_PATH= FORCE_SCRIPT_NAME= STATIC_URL=/static/ python manage.py test accounts reading
```

75 tests in each app: allowlist matching, pipeline, login/logout/throttle/redirect safety, set-password link
single use, admin invite and resend, the auth gate, per-user history isolation, SSO start URL, and the
anonymous baseline that must stay unchanged with the switch off.
