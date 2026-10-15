# Auth, groups and managed library — build log

Living document for adding University SSO, groups and group-restricted texts
to `academic-reading` (v1) and `academic-reading-eng` (v2).

- Full design: `docs/superpowers/specs/2026-10-14-auth-and-groups-design.md`
- SSO reference implementation: `/var/www/french-chat/frenchbot_django`
  (`accounts/social_pipeline.py`, `settings.py`)
- Email/account workflow reference:
  `/var/www/french-chat/django-user-registration-email-workflow.md`

## Status (2026-10-14)

| Step | v1 `academic-reading` | v2 `academic-reading-eng` |
|---|---|---|
| Design/spec | approved 2026-10-14 | same spec |
| Implementation plan | written, awaiting review (`superpowers/plans/2026-10-14-auth-and-groups-v1.md`) | after v1 is built |
| Built | no | no |
| Deployed dormant | no | no |
| Switched on (`AUTH_REQUIRED=true`) | no | no |

No application code has been changed yet. Both apps are live and anonymous.

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

_Nothing built yet. Entries are added here as each step is implemented,
including deployment commands, migrations run, and verification results._
