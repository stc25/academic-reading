# Auth, groups and managed library — build log

Living document for adding University SSO, groups and group-restricted texts
to `academic-reading` (v1) and `academic-reading-eng` (v2).

- Full design: `docs/superpowers/specs/2026-10-14-auth-and-groups-design.md`
- SSO reference implementation: `/var/www/french-chat/frenchbot_django`
  (`accounts/social_pipeline.py`, `settings.py`)
- Email/account workflow reference:
  `/var/www/french-chat/django-user-registration-email-workflow.md`

> **Update:** the login part of this plan (SSO + email accounts + auth gate + per-user history) is built for both apps
> on the `auth` branch and documented in `docs/LOGIN.md`. Groups and the database-managed library below remain unbuilt.

## Status (2026-10-16, `auth` branch only)

| Step | v1 `academic-reading` | v2 `academic-reading-eng` |
|---|---|---|
| Design/spec | `specs/2026-10-14-auth-and-groups-design.md`, superseded in part by `specs/2026-10-16-groups-and-library-design.md` | same |
| Sign-in (SSO + email, allowlist, per-user history) | built, deployed on lcapps | built, deployed on lcapps |
| Groups + group-restricted database library | **built** on `feature/groups-library` (126 tests) | **built** on `feature/groups-library` (128 tests) |
| Deployed on lcapps | no | no |

The live `cnlp` apps run `main` and are not touched. Anonymous mode is retired on this branch: sign-in is mandatory
and signed-out visitors see no texts. How to use groups: `docs/LOGIN.md`, section "Groups and texts".

## Decisions so far

- Order: v1 first, then v2.
- SSO: Microsoft Entra ID, **allowlist only** (as french-chat), via
  `social-auth-app-django`.
- Groups: Django `Group`; a user may be in several (access = union).
- Texts: no groups assigned = open to everyone; otherwise only to those
  groups. Admins only add texts and assign groups; teachers supply texts to
  admins and have no special rights.
- Library moves from files/manifest into a `LibraryText` DB model, with an
  idempotent import of the existing texts (v1: 37).
- Non-`.cam.ac.uk` users: admin-created accounts, account-created email with
  single-use set-password link, as in french-chat. Built dormant behind
  `EMAIL_PASSWORD_LOGIN_ENABLED`; SMTP details supplied later.
- Both apps are live: everything ships behind `AUTH_REQUIRED` (default off)
  and nothing changes for users until the user says to switch over.
- Entra client ID/secret and admin login to be supplied by the user later.

## Open items

- Spec review/approval, then implementation plan.
- Login-monitor integration details (`/var/www/login-monitor/README.md`).
- Assumption to confirm: after switch-over, no anonymous browsing.

## Build log

- 2026-10-16: groups and the database library built for v1 then v2 (`LibraryText`, `reading.access`, `GroupAccess`,
  `AllowedLogin.groups` synced at login, `import_library`, admin with bulk actions, mandatory sign-in with a 503 page
  when no sign-in method is configured). Not yet deployed. Deploy: pull, `docker compose up -d --build`, then
  `docker compose exec <app> python manage.py import_library --check`.
