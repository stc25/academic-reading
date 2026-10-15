# Auth, Groups and Managed Library — v1 (`academic-reading`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Cambridge Entra ID SSO (allowlist only), Django-group-restricted library texts, an admin-managed text library, and dormant email/password login to the live `academic-reading` app, all behind an `AUTH_REQUIRED` switch that ships off.

**Architecture:** Stock `django.contrib.auth` users (username = lower-cased email) — no custom user model and no session bridge (french-chat needed one only because it already had its own `User`; this app has none). A new `accounts` app holds `AllowedLogin`, the social-auth pipeline, login/logout/set-password views, an auth-gate middleware and the email service. `reading` gains a `LibraryText` model (+ `groups` M2M), a `library.py` loader that is the single source of truth for "which texts may this user see", and a `user` FK on `ReadingSession`. Nothing changes for current users until `AUTH_REQUIRED=true`.

**Tech Stack:** Django 5.1, `social-auth-app-django>=6.0.0` (AzureADTenantOAuth2), `django-unfold>=0.64.0`, MariaDB (sqlite for tests), Docker via the shared `/var/www/cnlp-docker-hosting` compose.

**Spec:** `/var/www/academic-reading/docs/superpowers/specs/2026-10-14-auth-and-groups-design.md` (approved). Build log: `/var/www/academic-reading/docs/AUTH_AND_GROUPS.md`.

**Scope note:** This plan covers v1 only. v2 (`academic-reading-eng`) is ported in a **separate plan written after v1 is built and verified**, because v2's text model (`sources/` + `source.cfg`, derived language/level) needs its own audit (spec §4.4).

## Conventions used below

- `APP` = `/var/www/academic-reading/academic-reading/academic_reading_django`
- Test command (run from `APP`; the empty `DATABASE_URL` forces sqlite — `load_dotenv` does not override an already-set variable):
  `DATABASE_URL= PUBLIC_PATH= FORCE_SCRIPT_NAME= STATIC_URL=/static/ ../.django-venv/bin/python manage.py test <label> -v 2` (also blank `PUBLIC_PATH`/`FORCE_SCRIPT_NAME` and set `STATIC_URL=/static/`, or `.env`'s prefix 404s every test-client request)
- **There is no git repo.** Where a normal plan says "commit", this plan says **Checkpoint**: run the full test suite and append one line to the Build log in `/var/www/academic-reading/docs/AUTH_AND_GROUPS.md`. (If the user runs `git init` first, commit at those points instead.)
- Live app: **never** restart/rebuild the production container except in Task 11, and only after the user confirms at that moment.

## Global Constraints

- Apps stay at their current subpaths; Django adds the prefix via `FORCE_SCRIPT_NAME` — always use `reverse()`/`{% url %}`, never literal paths.
- `AUTH_REQUIRED` default **false**; with it false every existing page behaves exactly as before (anonymous, `session_key`-scoped, file library).
- SSO tenant ID default `49a50445-bdfa-4b79-ade3-547b4f3986e9`; env vars `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` (same names as french-chat). SSO button hidden until both id and secret are set.
- Allowlist only: a non-allowlisted account is rejected **before** any user row is created.
- Passwords are never emailed; set-password link is single-use (Django token) and time-limited.
- Email backend defaults to file-based (nothing sent until SMTP supplied).
- Session/CSRF cookie names and paths stay app-specific (`arm_sessionid`, `arm_csrftoken`).
- Admin site at `django-admin/` (same convention as french-chat); Entra redirect URI will be `https://cnlp.langcen.cam.ac.uk/academic-reading/auth/sso/complete/azuread-tenant-oauth2/`.
- Texts with no groups are open to all authenticated users; staff see every active text; `active=False` hides a text from everyone.
- Existing library text ids and `ReadingSession.source_ref` values (`lib:<id>`) must be preserved.
- Production DB (`mariadb_academic_reading_v1`) must be backed up before the first migration that touches it.

## Deliberate deviations from the spec (all narrower or safer; record in the build log)

1. **No unique-constraint change on `ReadingSession`** (spec §4.5). Django's `login()` cycles the session key on user change, so `(session_key, source_ref)` can never collide across users; auth-on lookups are by `(user, source_ref)` and the existing constraint stays. Avoids a risky migration on live data.
2. **Account-created email is sent from the admin `save_model` hook, not a `post_save` signal** (spec §4.6). SSO-created users also have unusable passwords and must *not* be emailed; a signal cannot tell them apart from admin-invited users.
3. **`LIBRARY_SOURCE` env switch (`files` default | `db`)** in addition to `AUTH_REQUIRED`, so the DB import can be verified live before the library is read from the DB. `AUTH_REQUIRED=true` with `LIBRARY_SOURCE=files` is refused at startup (groups would be silently ignored).
4. **Allowlist identifiers also accept a bare CRSid** (e.g. `abc123`, only for `@cam.ac.uk` emails), matching the other apps (“allowlist same as other apps”); the spec listed only email and `@domain`.

## Review Focus

Failure modes the spec implies but that no spec sentence tests; each has a pinning test in the owning task.

1. **Deactivated user via SSO** — `is_active=False` account on the allowlist must be refused, not logged in (Task 4).
2. **Open redirect via `?next=`** on login — must only follow same-host URLs (Task 5).
3. **Email/password login for a `@cam.ac.uk` address** — must be refused (“use Cambridge sign-in”), and unusable-password accounts must never authenticate (Task 5).
4. **Case/whitespace in emails** — `Abc123@Cam.ac.uk`, trailing spaces in allowlist entries must still match (Task 3).
5. **Access revoked after a text was opened** — a user's existing reading history for a text later restricted/deactivated stays readable by its owner (content is already in their own history row); but the text vanishes from the library and cannot be newly opened (Task 9).

---

### Task 1: Dependencies, test harness, baseline regression

**Files:**
- Modify: `APP/requirements.txt`
- Modify: `APP/academic_reading_django/settings.py` (test-only static storage)
- Create: `APP/reading/tests/__init__.py` (**already exists** — created by the reply-cache feature, along with `reading/tests/test_reply_cache.py` and `reading/management/`; keep them)
- Create: `APP/reading/tests/test_baseline.py`

**Interfaces:**
- Produces: working test command; `test_baseline` pins today's anonymous behaviour (home lists 37 library texts; open creates a session; history shows it) — must stay green through every later task.

- [ ] **Step 1: Add dependencies and install into the dev venv**

Append to `APP/requirements.txt`:

```
django-unfold>=0.64.0
# >=6.0.0 pulls in social-auth-core>=5.0.0 (PyJWT CVE fixes), as in french-chat.
social-auth-app-django>=6.0.0
```

Run: `cd APP && ../.django-venv/bin/pip install -r requirements.txt`
Expected: installs `social-auth-app-django`, `social-auth-core`, `django-unfold` without error.

- [ ] **Step 2: Make static storage test-safe**

`CompressedManifestStaticFilesStorage` raises on `{% static %}` when no manifest exists, which breaks every template-rendering test. In `settings.py`, replace the `STORAGES = {...}` block with:

```python
import sys

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if "test" in sys.argv
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
```

- [ ] **Step 3: Write the baseline test**

`APP/reading/tests/__init__.py` empty. `APP/reading/tests/test_baseline.py`:

```python
"""Pins today's anonymous behaviour. Must pass unchanged at every task."""

from django.test import TestCase, override_settings
from django.urls import reverse

from reading.models import ReadingSession


@override_settings(AUTH_REQUIRED=False)
class AnonymousBaselineTests(TestCase):
    def test_home_lists_the_whole_bundled_library(self):
        response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 200)
        listed = sum(len(pool) for _, pool in response.context["groups"])
        self.assertEqual(listed, 37)

    def test_open_creates_a_session_and_history_shows_it(self):
        response = self.client.get(reverse("reading:open", kwargs={"source_ref": "de-01"}))
        self.assertEqual(response.status_code, 302)
        session = ReadingSession.objects.get()
        self.assertEqual(session.source_ref, "lib:de-01")
        history = self.client.get(reverse("reading:history"))
        self.assertContains(history, session.title)

    def test_health_is_open(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
```

- [ ] **Step 4: Run it**

Run: `cd APP && DATABASE_URL= ../.django-venv/bin/python manage.py test reading -v 2`
Expected: 3 tests PASS (this is a characterization test of existing code, so it passes immediately; if `37` differs, fix the number to what the app really returns and note it).

- [ ] **Step 5: Checkpoint** — append “Task 1: deps + baseline tests green” to the Build log.

---

### Task 2: Settings foundation (flags, auth apps, middleware stubs)

**Files:**
- Modify: `APP/academic_reading_django/settings.py`
- Create: `APP/accounts/__init__.py`, `APP/accounts/apps.py`
- Create: `APP/accounts/tests/__init__.py`, `APP/accounts/tests/test_settings.py`

**Interfaces:**
- Produces settings: `AUTH_REQUIRED: bool`, `EMAIL_PASSWORD_LOGIN_ENABLED: bool`, `LIBRARY_SOURCE: "files"|"db"`, `LOGIN_URL="accounts:login"`, `LOGIN_REDIRECT_URL="reading:home"`, `LOGOUT_REDIRECT_URL="accounts:login"`, the social-auth settings, email settings, `UNFOLD`.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Write the failing test** — `APP/accounts/tests/test_settings.py`:

```python
from django.conf import settings
from django.test import SimpleTestCase


class FlagDefaultsTests(SimpleTestCase):
    def test_flags_default_to_dormant(self):
        # Unless the environment sets them, everything ships off.
        self.assertFalse(settings.AUTH_REQUIRED)
        self.assertFalse(settings.EMAIL_PASSWORD_LOGIN_ENABLED)
        self.assertEqual(settings.LIBRARY_SOURCE, "files")

    def test_auth_apps_installed(self):
        for app in ("django.contrib.auth", "django.contrib.admin", "social_django", "accounts", "unfold"):
            self.assertIn(app, settings.INSTALLED_APPS)

    def test_session_cookie_names_unchanged(self):
        self.assertEqual(settings.SESSION_COOKIE_NAME, "arm_sessionid")
```

- [ ] **Step 2: Run, expect FAIL**: `DATABASE_URL= ../.django-venv/bin/python manage.py test accounts -v 2` → errors (`accounts` not a module / attribute missing).

- [ ] **Step 3: Create the app skeleton**

`APP/accounts/__init__.py` (empty). `APP/accounts/apps.py`:

```python
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
```
`APP/accounts/tests/__init__.py` empty.

- [ ] **Step 4: Edit `settings.py`.** Replace the module docstring's first paragraph line “No accounts, no admin — every reader is anonymous…” with: “Accounts are optional: with AUTH_REQUIRED unset every reader is anonymous and scoped to their session cookie; with it set, readers sign in (Entra SSO) and see only texts their groups may read.” Replace `INSTALLED_APPS` and `MIDDLEWARE` blocks and the `TEMPLATES` context processors, and append the new sections:

```python
def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes", "on")


# ── Feature switches (everything ships dormant) ─────────────────────────────
AUTH_REQUIRED = _flag("AUTH_REQUIRED")
EMAIL_PASSWORD_LOGIN_ENABLED = _flag("EMAIL_PASSWORD_LOGIN_ENABLED")
# "files": read texts/manifest.json (today). "db": read LibraryText rows.
LIBRARY_SOURCE = os.getenv("LIBRARY_SOURCE", "files").strip().lower()
if AUTH_REQUIRED and LIBRARY_SOURCE != "db":
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "AUTH_REQUIRED=true needs LIBRARY_SOURCE=db: group restrictions only "
        "exist on database texts and would be silently ignored otherwise."
    )

INSTALLED_APPS = [
    # "unfold" must precede "django.contrib.admin" so its templates win.
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "django.contrib.messages",
    "social_django",
    "accounts",
    "reading.apps.ReadingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
    "accounts.middleware.AuthRequiredMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

In `TEMPLATES[0]["OPTIONS"]["context_processors"]` add `"django.contrib.auth.context_processors.auth"` and `"accounts.context_processors.auth_flags"`.

Append at the end of the file:

```python
# ── University Microsoft sign-in (Entra ID) ─────────────────────────────────
# Same tenant and env-var names as french-chat. The button stays hidden until
# both KEY and SECRET are set (see accounts.views.login_view).
AUTHENTICATION_BACKENDS = [
    "social_core.backends.azuread_tenant.AzureADTenantOAuth2",
    "django.contrib.auth.backends.ModelBackend",
]
SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID = os.getenv(
    "AZURE_TENANT_ID", "49a50445-bdfa-4b79-ade3-547b4f3986e9"
)
SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY = os.getenv("AZURE_CLIENT_ID", "")
SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL = True
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "accounts.pipeline.enforce_allowlist",
    "social_core.pipeline.social_auth.social_user",
    # Reuse an admin-created account with the same email instead of cloning it.
    "social_core.pipeline.social_auth.associate_by_email",
    "social_core.pipeline.user.get_username",
    "social_core.pipeline.user.create_user",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
    "accounts.pipeline.sync_groups",
)
SOCIAL_AUTH_LOGIN_ERROR_URL = "accounts:login"
SOCIAL_AUTH_RAISE_EXCEPTIONS = False
RAISE_EXCEPTIONS = DEBUG

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "reading:home"
LOGOUT_REDIRECT_URL = "accounts:login"
# Admin-created accounts get a set-password link; give it a week.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 7

# Behind Caddy: trust the proxy's scheme so absolute URLs (SSO redirect URI,
# emailed links) are https.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ── Email (account-created / set-password emails; dormant until enabled) ────
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.filebased.EmailBackend")
EMAIL_FILE_PATH = os.getenv("EMAIL_FILE_PATH", str(BASE_DIR / "sent_emails"))
Path(EMAIL_FILE_PATH).mkdir(parents=True, exist_ok=True)
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _flag("EMAIL_USE_TLS")
EMAIL_USE_SSL = _flag("EMAIL_USE_SSL")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@localhost")

UNFOLD = {
    "SITE_TITLE": "Academic Reading Admin",
    "SITE_HEADER": "Academic Reading",
    "SITE_SUBHEADER": "Library, groups and sign-in",
    "SITE_URL": PUBLIC_PATH or "/",
}
```

Also change the `SESSION_COOKIE_AGE` comment (“a no-login history feature”) to “a long-lived history cookie”. `SESSION_COOKIE_SECURE` is only set when `DEBUG` is false; tests run with `DJANGO_DEBUG` unset → secure cookies in the test client are fine (the test client ignores `Secure`).

Create `APP/accounts/context_processors.py`:

```python
from django.conf import settings


def auth_flags(request):
    return {
        "auth_required": settings.AUTH_REQUIRED,
        "sso_enabled": bool(
            settings.SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY
            and settings.SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET
        ),
        "password_login_enabled": settings.EMAIL_PASSWORD_LOGIN_ENABLED,
    }
```

Create a placeholder `APP/accounts/middleware.py` so settings import works (real body in Task 5):

```python
class AuthRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)
```

- [ ] **Step 5: Run** `DATABASE_URL= ../.django-venv/bin/python manage.py test accounts reading` → FAIL on `social_django` URLs? No — URLs are added in Task 5; settings test only. Expected: `accounts` 3 tests PASS; `reading` baseline still PASS **except** templates now need nothing new. If `reading` fails because `accounts:login` is unresolved, that is Task 5's job — but baseline must not render it with `AUTH_REQUIRED=False`; fix any such coupling now.

- [ ] **Step 6: Create tables and check**: `DATABASE_URL= ../.django-venv/bin/python manage.py check` → “no issues”.

- [ ] **Step 7: Checkpoint.**

---

### Task 3: `AllowedLogin` model

**Files:**
- Create: `APP/accounts/models.py`, `APP/accounts/migrations/__init__.py` (+ generated `0001_initial.py`)
- Create: `APP/accounts/tests/test_allowedlogin.py`

**Interfaces:**
- Produces: `AllowedLogin(identifier: str unique lower-cased, groups: M2M[auth.Group], matched_user: OneToOne[User]|None, created_at)`; `AllowedLogin.matches(email: str) -> list[AllowedLogin]` (all entries matching the email: exact email, `@domain`, or — only for `@cam.ac.uk` — bare CRSid).

- [ ] **Step 1: Failing tests** — `test_allowedlogin.py`:

```python
from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import AllowedLogin


class MatchTests(TestCase):
    def test_exact_email_matches_case_and_space_insensitively(self):
        AllowedLogin.objects.create(identifier="  Abc123@Cam.ac.uk ")
        self.assertEqual(len(AllowedLogin.matches("ABC123@cam.ac.uk")), 1)

    def test_domain_entry_matches_everyone_on_the_domain(self):
        AllowedLogin.objects.create(identifier="@ling.cam.ac.uk")
        self.assertEqual(len(AllowedLogin.matches("x@ling.cam.ac.uk")), 1)
        self.assertEqual(AllowedLogin.matches("x@other.cam.ac.uk"), [])

    def test_crsid_matches_only_cambridge_addresses(self):
        AllowedLogin.objects.create(identifier="abc123")
        self.assertEqual(len(AllowedLogin.matches("abc123@cam.ac.uk")), 1)
        self.assertEqual(AllowedLogin.matches("abc123@evil.example"), [])

    def test_multiple_matching_entries_are_all_returned(self):
        AllowedLogin.objects.create(identifier="abc123@cam.ac.uk")
        AllowedLogin.objects.create(identifier="@cam.ac.uk")
        self.assertEqual(len(AllowedLogin.matches("abc123@cam.ac.uk")), 2)

    def test_no_match_and_blank(self):
        self.assertEqual(AllowedLogin.matches(""), [])
        self.assertEqual(AllowedLogin.matches("nobody@cam.ac.uk"), [])

    def test_groups_attach(self):
        entry = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        entry.groups.add(Group.objects.create(name="Y1"))
        self.assertEqual(entry.groups.count(), 1)
```

- [ ] **Step 2: Run, expect FAIL** (`cannot import name AllowedLogin`).

- [ ] **Step 3: Implement** `APP/accounts/models.py`:

```python
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models

CAM_DOMAIN = "cam.ac.uk"


class AllowedLogin(models.Model):
    """One allowlist entry: an exact email, a bare CRSid, or an ``@domain``.

    SSO sign-in is refused unless the signed-in email matches at least one
    entry. On every sign-in the user is added to the groups of *all* matching
    entries (additive — groups an admin added by hand are never removed).
    """

    identifier = models.CharField(
        max_length=255,
        unique=True,
        help_text="An email (abc123@cam.ac.uk), a CRSid (abc123), or a whole domain (@dept.cam.ac.uk).",
    )
    groups = models.ManyToManyField(Group, blank=True, related_name="allowed_logins")
    matched_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="allowed_login",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["identifier"]

    def __str__(self) -> str:
        return self.identifier

    def save(self, *args, **kwargs) -> None:
        self.identifier = self.identifier.strip().lower()
        super().save(*args, **kwargs)

    @classmethod
    def matches(cls, email: str) -> list["AllowedLogin"]:
        email = (email or "").strip().lower()
        if "@" not in email:
            return []
        local, domain = email.split("@", 1)
        keys = {email, f"@{domain}"}
        if domain == CAM_DOMAIN:
            keys.add(local)
        return list(cls.objects.filter(identifier__in=keys))
```

- [ ] **Step 4:** `DATABASE_URL= ../.django-venv/bin/python manage.py makemigrations accounts` then run `test accounts` → all PASS.

- [ ] **Step 5: Checkpoint.**

---

### Task 4: SSO pipeline (`enforce_allowlist`, `sync_groups`, login report)

**Files:**
- Create: `APP/accounts/pipeline.py`, `APP/accounts/login_report.py`
- Create: `APP/accounts/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `AllowedLogin.matches`.
- Produces: `NotAllowlisted(AuthForbidden)`; `enforce_allowlist(strategy, details, backend, *args, **kwargs) -> {"allowed_entries": [pk, ...]}`; `sync_groups(strategy, details, backend, user=None, allowed_entries=None, *args, **kwargs) -> None`; `report_login(email: str, method: str) -> None` (fire-and-forget, identical to french-chat's).

- [ ] **Step 1: Copy the login reporter verbatim** from `/var/www/french-chat/frenchbot_django/accounts/login_report.py` to `APP/accounts/login_report.py` (no edits; it is env-gated by `MONITOR_URL`/`MONITOR_TOKEN`/`MONITOR_APP_NAME`).

- [ ] **Step 2: Failing tests** — `test_pipeline.py`:

```python
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase
from social_core.exceptions import AuthForbidden

from accounts import pipeline
from accounts.models import AllowedLogin


class EnforceAllowlistTests(TestCase):
    def test_rejects_unlisted_email_and_creates_nothing(self):
        with self.assertRaises(pipeline.NotAllowlisted):
            pipeline.enforce_allowlist(None, {"email": "stranger@cam.ac.uk"}, object())
        self.assertEqual(User.objects.count(), 0)

    def test_notallowlisted_is_an_authforbidden_with_helpful_message(self):
        exc = pipeline.NotAllowlisted(object())
        self.assertIsInstance(exc, AuthForbidden)
        self.assertIn("allowed list", str(exc))

    def test_rejects_missing_email(self):
        with self.assertRaises(pipeline.NotAllowlisted):
            pipeline.enforce_allowlist(None, {}, object())

    def test_accepts_listed_email_returning_entry_pks(self):
        entry = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        out = pipeline.enforce_allowlist(None, {"email": "A@cam.ac.uk"}, object())
        self.assertEqual(out["allowed_entries"], [entry.pk])


class SyncGroupsTests(TestCase):
    def setUp(self):
        self.g1 = Group.objects.create(name="Y1")
        self.g2 = Group.objects.create(name="Y2")
        self.user = User.objects.create_user("a@cam.ac.uk", "a@cam.ac.uk")

    def _run(self, user, entries):
        pipeline.sync_groups(None, {"email": "a@cam.ac.uk"}, object(), user=user,
                             allowed_entries=[e.pk for e in entries])

    def test_adds_union_of_all_matching_entries_groups(self):
        e1 = AllowedLogin.objects.create(identifier="a@cam.ac.uk"); e1.groups.add(self.g1)
        e2 = AllowedLogin.objects.create(identifier="@cam.ac.uk"); e2.groups.add(self.g2)
        self._run(self.user, [e1, e2])
        self.assertEqual(set(self.user.groups.all()), {self.g1, self.g2})

    def test_is_additive_never_removes_manual_groups(self):
        self.user.groups.add(self.g2)
        e1 = AllowedLogin.objects.create(identifier="a@cam.ac.uk"); e1.groups.add(self.g1)
        self._run(self.user, [e1])
        self.assertEqual(set(self.user.groups.all()), {self.g1, self.g2})

    def test_links_matched_user_to_the_specific_entry_not_the_domain_one(self):
        specific = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        domain = AllowedLogin.objects.create(identifier="@cam.ac.uk")
        self._run(self.user, [specific, domain])
        specific.refresh_from_db(); domain.refresh_from_db()
        self.assertEqual(specific.matched_user, self.user)
        self.assertIsNone(domain.matched_user)

    def test_inactive_user_is_refused(self):
        self.user.is_active = False
        self.user.save()
        e1 = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        with self.assertRaises(AuthForbidden):
            self._run(self.user, [e1])

    def test_reports_the_login_as_sso(self):
        e1 = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        with mock.patch("accounts.pipeline.report_login") as report:
            self._run(self.user, [e1])
        report.assert_called_once_with("a@cam.ac.uk", "sso")
```

- [ ] **Step 3: Run, expect FAIL** (`accounts.pipeline` missing).

- [ ] **Step 4: Implement** `APP/accounts/pipeline.py`:

```python
"""python-social-auth pipeline steps for University Microsoft (Entra ID) SSO.

``enforce_allowlist`` runs right after social-core's ``auth_allowed`` and
refuses the sign-in before any user/social-auth row exists. ``sync_groups``
runs last, once a stock ``auth.User`` has been found or created.
"""

from __future__ import annotations

from social_core.exceptions import AuthForbidden

from .login_report import report_login
from .models import AllowedLogin


class NotAllowlisted(AuthForbidden):
    """SocialAuthExceptionMiddleware surfaces str(exception) as a Django
    message and redirects to SOCIAL_AUTH_LOGIN_ERROR_URL."""

    def __str__(self) -> str:
        return (
            "Your Cambridge account isn't on the allowed list for this "
            "service. Contact your teacher or the Language Centre."
        )


def enforce_allowlist(strategy, details, backend, *args, **kwargs):
    entries = AllowedLogin.matches(details.get("email") or "")
    if not entries:
        raise NotAllowlisted(backend)
    return {"allowed_entries": [entry.pk for entry in entries]}


def sync_groups(strategy, details, backend, user=None, allowed_entries=None, *args, **kwargs):
    if user is None:
        return
    if not user.is_active:
        raise AuthForbidden(backend)

    email = (details.get("email") or "").strip().lower()
    if not user.email:
        user.email = email
        user.save(update_fields=["email"])

    entries = AllowedLogin.objects.filter(pk__in=allowed_entries or [])
    for entry in entries:
        user.groups.add(*entry.groups.all())

    # Only a specific (non-domain) entry can belong to one person.
    specific = entries.exclude(identifier__startswith="@").first()
    if specific and specific.matched_user_id != user.id:
        specific.matched_user = user
        specific.save(update_fields=["matched_user"])

    report_login(email or user.email, "sso")
```

- [ ] **Step 5: Run** `test accounts` → all PASS.

- [ ] **Step 6: Checkpoint.**

---

### Task 5: Login/logout/set-password views, auth-gate middleware, URLs

**Files:**
- Modify: `APP/accounts/middleware.py` (real body), `APP/academic_reading_django/urls.py`
- Create: `APP/accounts/views.py`, `APP/accounts/urls.py`, `APP/accounts/throttle.py`
- Create: `APP/accounts/templates/accounts/login.html`, `.../password_set.html`
- Create: `APP/accounts/tests/test_views.py`, `APP/accounts/tests/test_middleware.py`

**Interfaces:**
- Consumes: settings flags (Task 2), `report_login` (Task 4).
- Produces URL names (namespace `accounts`): `login`, `logout` (POST), `password_reset_confirm` (kwargs `uidb64`, `token`); social-auth at `auth/sso/` (namespace `social`; begin = `social:begin` with `backend="azuread-tenant-oauth2"`). `throttled(request, scope, email) -> bool`.

- [ ] **Step 1: Failing middleware tests** — `test_middleware.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(AUTH_REQUIRED=True, LIBRARY_SOURCE="db")
class AuthGateTests(TestCase):
    def test_anonymous_is_redirected_to_login_with_next(self):
        response = self.client.get(reverse("reading:home"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("accounts:login")))
        self.assertIn("next=", response["Location"])

    def test_exempt_paths_stay_open(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)

    def test_signed_in_user_passes(self):
        user = User.objects.create_user("a@cam.ac.uk", "a@cam.ac.uk")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("reading:home")).status_code, 200)


@override_settings(AUTH_REQUIRED=False)
class DormantGateTests(TestCase):
    def test_anonymous_passes_when_switch_is_off(self):
        self.assertEqual(self.client.get(reverse("reading:home")).status_code, 200)
```
(`reading:home` with `AUTH_REQUIRED=True` renders after Task 9; until then the third test may need `LIBRARY_SOURCE=db` handling — Task 7/9 make it pass. Mark it expected to pass only from Task 9 onward and skip-check it now; the first two must pass in this task.)

- [ ] **Step 2: Failing view tests** — `test_views.py`:

```python
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
class PasswordLoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ext@example.org", "ext@example.org", "s3cret-pass-xyz")

    def _post(self, email, password, **extra):
        return self.client.post(reverse("accounts:login"), {"email": email, "password": password, **extra})

    def test_valid_credentials_log_in_and_redirect_home(self):
        response = self._post("EXT@example.org", "s3cret-pass-xyz")
        self.assertRedirects(response, reverse("reading:home"), fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_password_rejected(self):
        response = self._post("ext@example.org", "nope")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unusable_password_account_cannot_log_in(self):
        invited = User.objects.create_user("inv@example.org", "inv@example.org")
        invited.set_unusable_password(); invited.save()
        self.assertNotIn("_auth_user_id", self._post("inv@example.org", "").client.session)

    def test_cambridge_addresses_are_refused_password_login(self):
        User.objects.create_user("abc@cam.ac.uk", "abc@cam.ac.uk", "s3cret-pass-xyz")
        response = self._post("abc@cam.ac.uk", "s3cret-pass-xyz")
        self.assertContains(response, "Cambridge sign-in")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_next_to_other_host_is_ignored(self):
        response = self._post("ext@example.org", "s3cret-pass-xyz", next="https://evil.example/x")
        self.assertRedirects(response, reverse("reading:home"), fetch_redirect_response=False)

    def test_next_same_site_is_followed(self):
        target = reverse("reading:history")
        response = self._post("ext@example.org", "s3cret-pass-xyz", next=target)
        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_throttle_blocks_after_too_many_attempts(self):
        for _ in range(12):
            self._post("ext@example.org", "bad")
        self.assertEqual(self._post("ext@example.org", "s3cret-pass-xyz").status_code, 429)


class FlagOffTests(TestCase):
    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=False)
    def test_password_form_absent_and_post_ignored(self):
        User.objects.create_user("ext@example.org", "ext@example.org", "s3cret-pass-xyz")
        page = self.client.get(reverse("accounts:login"))
        self.assertNotContains(page, 'name="password"')
        self.client.post(reverse("accounts:login"), {"email": "ext@example.org", "password": "s3cret-pass-xyz"})
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="", SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="")
    def test_sso_button_hidden_without_credentials(self):
        self.assertNotContains(self.client.get(reverse("accounts:login")), "Sign in with Cambridge")

    @override_settings(SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY="id", SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET="s")
    def test_sso_button_shown_with_credentials(self):
        self.assertContains(self.client.get(reverse("accounts:login")), "Sign in with Cambridge")


class LogoutTests(TestCase):
    def test_logout_requires_post_and_clears_session(self):
        user = User.objects.create_user("a@x.org", "a@x.org", "pw-abc-12345")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class SetPasswordTests(TestCase):
    def test_link_sets_password_once_then_expires(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.create_user("n@example.org", "n@example.org")
        user.set_unusable_password(); user.save()
        url = reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user)})
        page = self.client.get(url, follow=True)
        set_url = page.redirect_chain[-1][0]
        self.client.post(set_url, {"new_password1": "a-Long-pass-9921", "new_password2": "a-Long-pass-9921"})
        user.refresh_from_db()
        self.assertTrue(user.check_password("a-Long-pass-9921"))
        # token is now invalid (password hash changed)
        self.assertContains(self.client.get(url), "no longer valid")
```

- [ ] **Step 3: Run, expect FAIL** (no URLs/views).

- [ ] **Step 4: Implement throttle** — `APP/accounts/throttle.py` (adapted from french-chat's `_throttled`):

```python
from django.core.cache import cache

_WINDOW = 15 * 60
_PER_IP = 30
_PER_EMAIL = 10


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def throttled(request, scope: str, email: str) -> bool:
    """Count this attempt; True once the IP or email is over its limit.

    Per-process cache, so the effective limit scales with gunicorn workers —
    enough to stop mass guessing (same trade-off as french-chat).
    """
    for key, limit in (
        (f"throttle:{scope}:ip:{_client_ip(request)}", _PER_IP),
        (f"throttle:{scope}:email:{email.strip().lower()}", _PER_EMAIL),
    ):
        cache.add(key, 0, _WINDOW)
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, _WINDOW)
            count = 1
        if count > limit:
            return True
    return False
```
Note: tests share the locmem cache — clear it in `PasswordLoginTests.setUp` (`from django.core.cache import cache; cache.clear()`); add that line.

- [ ] **Step 5: Implement views** — `APP/accounts/views.py`:

```python
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import PasswordResetConfirmView
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .login_report import report_login
from .throttle import throttled


def _safe_next(request) -> str:
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return reverse(settings.LOGIN_REDIRECT_URL)


def login_view(request):
    next_url = _safe_next(request)
    if request.user.is_authenticated:
        return redirect(next_url)

    error = ""
    status = 200
    if request.method == "POST" and settings.EMAIL_PASSWORD_LOGIN_ENABLED:
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        if throttled(request, "login", email):
            error, status = "Too many attempts. Please try again later.", 429
        elif email.endswith("cam.ac.uk"):
            error = "Cambridge accounts must use Cambridge sign-in."
        else:
            user = authenticate(request, username=email, password=password)
            if user is not None and user.is_active:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                report_login(user.email or email, "email")
                return redirect(next_url)
            error = "Incorrect email or password."
    return render(request, "accounts/login.html", {"error": error, "next": next_url}, status=status)


@require_POST
def logout_view(request):
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


class PasswordSetView(PasswordResetConfirmView):
    template_name = "accounts/password_set.html"
    success_url = reverse_lazy("accounts:login")
```
(`email.endswith("cam.ac.uk")` also catches `x@ling.cam.ac.uk`. `"@evilcam.ac.uk"` would be refused too — acceptable, errs safe.)

`APP/accounts/urls.py`:

```python
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password-set/<uidb64>/<token>/", views.PasswordSetView.as_view(), name="password_reset_confirm"),
]
```

Edit `academic_reading_django/urls.py` — imports `from django.contrib import admin`; add before the final include:

```python
    path("django-admin/", admin.site.urls),
    path("auth/sso/", include("social_django.urls", namespace="social")),
    path("auth/", include("accounts.urls")),
```

- [ ] **Step 6: Middleware** — replace `APP/accounts/middleware.py`:

```python
from django.conf import settings
from django.contrib.auth.views import redirect_to_login

# Path prefixes (after the script prefix) that never require sign-in.
EXEMPT_PREFIXES = ("/health", "/static/", "/django-admin/", "/auth/")


class AuthRequiredMiddleware:
    """When AUTH_REQUIRED is on, send anonymous visitors to the login page.

    The switch is read per request so tests (and a restart-free toggle in
    tests) behave; in production it is fixed at process start.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.AUTH_REQUIRED
            and not request.user.is_authenticated
            and not request.path_info.startswith(EXEMPT_PREFIXES)
        ):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)
```

- [ ] **Step 7: Templates.** `APP/accounts/templates/accounts/login.html`:

```django
{% extends "reading/base.html" %}
{% block title %}Sign in{% endblock %}
{% block content %}
<h1>Sign in</h1>
{% if error %}<div class="callout error">{{ error }}</div>{% endif %}

{% if sso_enabled %}
  <p><a class="btn btn-primary" href="{% url 'social:begin' 'azuread-tenant-oauth2' %}{% if next %}?next={{ next|urlencode }}{% endif %}">Sign in with Cambridge (Microsoft)</a></p>
{% else %}
  <p class="callout">Cambridge sign-in is not yet available.</p>
{% endif %}

{% if password_login_enabled %}
  <h2>Not at Cambridge?</h2>
  <form method="post" action="{% url 'accounts:login' %}">
    {% csrf_token %}
    <input type="hidden" name="next" value="{{ next }}">
    <div><label for="email">Email</label>
      <input type="email" id="email" name="email" required autocomplete="username"></div>
    <div><label for="password">Password</label>
      <input type="password" id="password" name="password" required autocomplete="current-password"></div>
    <button type="submit" class="btn btn-primary">Sign in</button>
  </form>
{% endif %}
{% endblock %}
```

`APP/accounts/templates/accounts/password_set.html`:

```django
{% extends "reading/base.html" %}
{% block title %}Set your password{% endblock %}
{% block content %}
{% if validlink %}
  <h1>Set your password</h1>
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit" class="btn btn-primary">Save password</button>
  </form>
{% else %}
  <h1>Link not valid</h1>
  <p class="callout error">This link is no longer valid — it may have been used already or expired.
    Ask the Language Centre to send you a new one.</p>
{% endif %}
{% endblock %}
```

Edit `reading/templates/reading/base.html`: wrap `<nav>…</nav>` in `{% if user.is_authenticated or not auth_required %}`; inside it, after the History link, add:

```django
        {% if user.is_authenticated %}
          <form method="post" action="{% url 'accounts:logout' %}" style="display:inline">
            {% csrf_token %}
            <span class="whoami">{{ user.email|default:user.username }}</span>
            <button type="submit" class="linklike">Sign out</button>
          </form>
        {% endif %}
```
and add to `reading/static/reading/css/app.css`: `.linklike{background:none;border:0;padding:0;color:inherit;text-decoration:underline;cursor:pointer;font:inherit}.whoami{margin-right:.5rem;opacity:.8}`.
(The password_set test's `follow=True` redirect chain: Django's confirm view redirects the token URL to a `set-password` session URL — the test reads the last hop; if the chain is empty on a given Django version, assert on the `200` page instead and post to the same URL.)

- [ ] **Step 8: Run** `test accounts reading` → all PASS except the `signed_in_user_passes` case, which depends on Task 9; confirm its failure reason is the library/view wiring, not a gate bug (it should return 200 once `LIBRARY_SOURCE=db` library loading exists; in the meantime `load_library()` still works because `reading.views` still reads files — so it should in fact pass now. If it passes, good.)

- [ ] **Step 9: Checkpoint.**

---

### Task 6: Admin (unfold) — users, groups, allowlist, set-password email

**Files:**
- Create: `APP/accounts/admin.py`, `APP/accounts/services.py`
- Create: `APP/accounts/templates/accounts/email/account_created_subject.txt`, `account_created.txt`, `account_created.html`
- Create: `APP/accounts/tests/test_admin.py`

**Interfaces:**
- Consumes: URL name `accounts:password_reset_confirm` (Task 5), `AllowedLogin` (Task 3).
- Produces: `send_account_created_email(user, request=None) -> None`; admin registrations for `User`, `Group`, `AllowedLogin`; admin action `resend_set_password_email`.

- [ ] **Step 1: Failing tests** — `test_admin.py`:

```python
from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AllowedLogin
from accounts.services import send_account_created_email


class EmailServiceTests(TestCase):
    def test_email_has_set_password_link_and_no_password(self):
        user = User.objects.create_user("n@example.org", "n@example.org", first_name="Ann <b>")
        send_account_created_email(user)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["n@example.org"])
        self.assertIn("/auth/password-set/", message.body)
        html = message.alternatives[0][0]
        self.assertNotIn("<b>", html)  # name is HTML-escaped


class AdminCreateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root", "root@x.org", "pw-root-12345")
        self.client.force_login(self.admin)
        self.group = Group.objects.create(name="Y1")

    def _add(self):
        return self.client.post(reverse("admin:auth_user_add"), {
            "email": "New@Example.org", "first_name": "N", "last_name": "U", "groups": [self.group.pk]})

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
    def test_creating_user_makes_passwordless_account_and_sends_one_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            self._add()
        user = User.objects.get(username="new@example.org")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.email, "new@example.org")
        self.assertEqual(list(user.groups.all()), [self.group])
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=False)
    def test_no_email_while_the_feature_is_dormant(self):
        with self.captureOnCommitCallbacks(execute=True):
            self._add()
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
    def test_sso_style_user_creation_outside_admin_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            User.objects.create_user("sso@cam.ac.uk", "sso@cam.ac.uk")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_PASSWORD_LOGIN_ENABLED=True)
    def test_resend_action(self):
        user = User.objects.create_user("r@example.org", "r@example.org")
        self.client.post(reverse("admin:auth_user_changelist"),
                         {"action": "resend_set_password_email", "_selected_action": [user.pk]})
        self.assertEqual(len(mail.outbox), 1)


class AllowedLoginAdminTests(TestCase):
    def test_changelist_loads(self):
        admin = User.objects.create_superuser("root", "root@x.org", "pw-root-12345")
        self.client.force_login(admin)
        AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        self.assertEqual(self.client.get(reverse("admin:accounts_allowedlogin_changelist")).status_code, 200)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement the service** — `APP/accounts/services.py`:

```python
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def build_set_password_url(user, request=None) -> str:
    path = reverse(
        "accounts:password_reset_confirm",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    return request.build_absolute_uri(path) if request is not None else path


def send_account_created_email(user, request=None) -> None:
    """Tell an admin-created user to set their own password (single-use link;
    the password itself is never emailed)."""
    context = {"user": user, "set_password_url": build_set_password_url(user, request)}
    subject = render_to_string("accounts/email/account_created_subject.txt", context).strip()
    message = EmailMultiAlternatives(
        subject,
        render_to_string("accounts/email/account_created.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    message.attach_alternative(render_to_string("accounts/email/account_created.html", context), "text/html")
    message.send()
```

Templates:
`account_created_subject.txt`: `Your Academic Reading account`
`account_created.txt`:
```
Hello{% if user.first_name %} {{ user.first_name }}{% endif %},

An account has been created for you on Academic Reading (Cambridge Language Centre).
Set your password using this link (it can be used once and expires in 7 days):

{{ set_password_url }}

If you weren't expecting this, you can ignore this email.
```
`account_created.html`:
```django
<p>Hello{% if user.first_name %} {{ user.first_name }}{% endif %},</p>
<p>An account has been created for you on Academic Reading (Cambridge Language Centre).</p>
<p><a href="{{ set_password_url }}">Set your password</a> — the link can be used once and expires in 7 days.</p>
<p>If you weren't expecting this, you can ignore this email.</p>
```
(Django autoescapes `.html`; `.txt` rendered via `render_to_string` is also autoescaped — a URL with `&` is not present here, so fine. Check `{{ user.first_name }}` in the .txt: autoescape turns `<` into `&lt;` — harmless in plain text but ugly; wrap the txt body in `{% autoescape off %}…{% endautoescape %}`. The URL contains only base64/token chars.)

- [ ] **Step 4: Implement admin** — `APP/accounts/admin.py`:

```python
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db import transaction
from unfold.admin import ModelAdmin

from .models import AllowedLogin
from .services import send_account_created_email

admin.site.unregister(User)
admin.site.unregister(Group)


class InviteUserForm(forms.ModelForm):
    """Create an account with no password; the person sets their own via the
    emailed link. Username is always the lower-cased email."""

    email = forms.EmailField()

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "groups")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email = self.cleaned_data["email"]
        user.set_unusable_password()
        if commit:
            user.save()
            self.save_m2m()
        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    add_form = InviteUserForm
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "groups")}),)
    list_display = ("username", "first_name", "last_name", "is_staff", "is_active")
    actions = ["resend_set_password_email"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and settings.EMAIL_PASSWORD_LOGIN_ENABLED:
            transaction.on_commit(lambda: send_account_created_email(obj, request))

    @admin.action(description="Send set-password email")
    def resend_set_password_email(self, request, queryset):
        if not settings.EMAIL_PASSWORD_LOGIN_ENABLED:
            self.message_user(request, "Email/password login is not enabled.", messages.WARNING)
            return
        for user in queryset.exclude(email=""):
            send_account_created_email(user, request)
        self.message_user(request, "Set-password emails sent.")


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(AllowedLogin)
class AllowedLoginAdmin(ModelAdmin):
    list_display = ("identifier", "group_names", "matched_user", "created_at")
    search_fields = ("identifier",)
    filter_horizontal = ("groups",)

    @admin.display(description="Groups")
    def group_names(self, obj):
        return ", ".join(group.name for group in obj.groups.all())
```
If unfold's `ModelAdmin` MRO clashes with `BaseUserAdmin` forms in the installed unfold version, follow unfold's documented pattern (`from unfold.forms import AdminPasswordChangeForm, UserChangeForm`; set `form`, `change_password_form`) — keep `add_form = InviteUserForm`.

- [ ] **Step 5: Run** `test accounts` → all PASS. Then run `manage.py check`.

- [ ] **Step 6: Checkpoint.**

---

### Task 7: `LibraryText` model, loader, visibility rule, import command

**Files:**
- Modify: `APP/reading/models.py`
- Create: `APP/reading/library.py`
- Create: `APP/reading/management/__init__.py`, `management/commands/__init__.py`, `management/commands/import_library.py`
- Create: `APP/reading/tests/test_library.py`

**Interfaces:**
- Consumes: `Text` dataclass and `load_library()` (`reading/logic/corpus.py`).
- Produces: `LibraryText` model; `library.load_texts(user=None) -> list[Text]` (sorted by id; file library when `LIBRARY_SOURCE != "db"`; DB rows respecting groups/staff/active when `db`); `library.get_text(source_ref, user=None) -> Text | None`; `manage.py import_library [--overwrite]`.

- [ ] **Step 1: Failing tests** — `test_library.py`:

```python
from io import StringIO

from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings

from reading import library
from reading.models import LibraryText


def _text(ref, **kw):
    return LibraryText.objects.create(source_ref=ref, title=ref, lang="de", body="Hallo Welt.", **kw)


@override_settings(LIBRARY_SOURCE="db", AUTH_REQUIRED=True)
class VisibilityTests(TestCase):
    def setUp(self):
        self.g1, self.g2 = Group.objects.create(name="Y1"), Group.objects.create(name="Y2")
        self.open = _text("open")
        self.y1 = _text("y1"); self.y1.groups.add(self.g1)
        self.y2 = _text("y2"); self.y2.groups.add(self.g2)
        self.off = _text("off", active=False)
        self.user = User.objects.create_user("a@x.org", "a@x.org")

    def ids(self, user):
        return [t.id for t in library.load_texts(user)]

    def test_no_groups_means_open_to_everyone(self):
        self.assertEqual(self.ids(self.user), ["open"])

    def test_member_sees_their_groups_texts_only(self):
        self.user.groups.add(self.g1)
        self.assertEqual(self.ids(self.user), ["open", "y1"])

    def test_union_over_several_groups_without_duplicates(self):
        self.y1.groups.add(self.g2)  # y1 now in both groups
        self.user.groups.add(self.g1, self.g2)
        self.assertEqual(self.ids(self.user), ["open", "y1", "y2"])

    def test_staff_sees_every_active_text_but_not_inactive(self):
        staff = User.objects.create_user("s@x.org", "s@x.org", is_staff=True)
        self.assertEqual(self.ids(staff), ["open", "y1", "y2"])

    def test_anonymous_sees_nothing_when_auth_required(self):
        self.assertEqual(self.ids(AnonymousUser()), [])

    def test_get_text_respects_visibility(self):
        self.assertIsNone(library.get_text("y1", self.user))
        self.assertIsNone(library.get_text("off", self.user))
        self.assertEqual(library.get_text("open", self.user).body, "Hallo Welt.")


@override_settings(LIBRARY_SOURCE="db", AUTH_REQUIRED=False)
class DormantDbTests(TestCase):
    def test_restrictions_ignored_when_auth_off(self):
        text = _text("y1"); text.groups.add(Group.objects.create(name="Y1"))
        self.assertEqual([t.id for t in library.load_texts(AnonymousUser())], ["y1"])


@override_settings(LIBRARY_SOURCE="files")
class FilesModeTests(TestCase):
    def test_file_library_is_unchanged(self):
        self.assertEqual(len(library.load_texts(None)), 37)


class ImportTests(TestCase):
    def test_import_creates_all_texts_and_is_idempotent(self):
        call_command("import_library", stdout=StringIO())
        self.assertEqual(LibraryText.objects.count(), 37)
        row = LibraryText.objects.get(source_ref="de-01")
        row.title = "Edited by an admin"; row.save()
        call_command("import_library", stdout=StringIO())
        self.assertEqual(LibraryText.objects.count(), 37)
        row.refresh_from_db()
        self.assertEqual(row.title, "Edited by an admin")  # not overwritten

    def test_overwrite_flag_resets_content_but_keeps_groups(self):
        call_command("import_library", stdout=StringIO())
        row = LibraryText.objects.get(source_ref="de-01")
        group = Group.objects.create(name="G"); row.groups.add(group)
        row.title = "x"; row.save()
        call_command("import_library", "--overwrite", stdout=StringIO())
        row.refresh_from_db()
        self.assertNotEqual(row.title, "x")
        self.assertEqual(list(row.groups.all()), [group])

    @override_settings(LIBRARY_SOURCE="db")
    def test_imported_library_equals_file_library(self):
        from reading.logic.corpus import load_library
        call_command("import_library", stdout=StringIO())
        db = {t.id: t for t in library.load_texts(None)}
        for f in load_library()[1]:
            d = db[f.id]
            for attr in ("lang", "title", "body", "author", "year", "topic", "copyright",
                         "excerpt", "source", "script", "register"):
                self.assertEqual(getattr(d, attr), getattr(f, attr), (f.id, attr))
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Model.** Append to `reading/models.py` (after the existing imports add `from django.contrib.auth.models import Group`, `from django.conf import settings`):

```python
class LibraryText(models.Model):
    """A library text managed in the admin.

    ``groups`` empty = open to every signed-in user; otherwise only members
    of at least one listed group (staff see all). ``active=False`` hides it
    from everyone without deleting it.
    """

    source_ref = models.SlugField(
        max_length=100, unique=True, allow_unicode=False,
        help_text="Short unique id, e.g. de-12. Never change it once readers have opened the text.",
    )
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=300, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    lang = models.CharField(max_length=10, choices=list(LANG_NAMES.items()))
    topic = models.CharField(max_length=200, blank=True)
    register = models.CharField(max_length=50, blank=True)
    copyright = models.CharField(max_length=100, blank=True)
    excerpt = models.CharField(max_length=500, blank=True)
    source = models.CharField(max_length=500, blank=True)
    script = models.CharField(max_length=20, blank=True)
    body = models.TextField()
    active = models.BooleanField(default=True)
    groups = models.ManyToManyField(
        Group, blank=True, related_name="library_texts",
        help_text="Leave empty to make this text available to everyone.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_ref"]

    def __str__(self) -> str:
        return f"{self.source_ref} — {self.title}"
```
And add to `ReadingSession`:

```python
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name="reading_sessions",
    )
```
and an index `models.Index(fields=["user", "-created_at"])` in its `Meta.indexes`. Update module docstring: history is session-scoped until AUTH_REQUIRED, user-scoped after.

- [ ] **Step 4: Loader** — `APP/reading/library.py`:

```python
"""Which library texts may this user see? One answer, used everywhere."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q

from .logic.corpus import Text, load_library
from .models import LibraryText


def _to_text(row: LibraryText) -> Text:
    return Text(
        id=row.source_ref, lang=row.lang, title=row.title, body=row.body.strip(),
        author=row.author, year=row.year, topic=row.topic, copyright=row.copyright,
        excerpt=row.excerpt, source=row.source, script=row.script, register=row.register,
    )


def load_texts(user=None) -> list[Text]:
    if settings.LIBRARY_SOURCE != "db":
        return load_library()[1]

    rows = LibraryText.objects.filter(active=True)
    if settings.AUTH_REQUIRED:
        if user is None or not user.is_authenticated:
            return []
        if not user.is_staff:
            rows = rows.filter(
                Q(groups__isnull=True) | Q(groups__in=user.groups.all())
            ).distinct()
    return [_to_text(row) for row in rows.order_by("source_ref")]


def get_text(source_ref: str, user=None) -> Text | None:
    return next((t for t in load_texts(user) if t.id == source_ref), None)
```

- [ ] **Step 5: Import command** — `reading/management/commands/import_library.py`:

```python
from django.core.management.base import BaseCommand

from reading.logic.corpus import load_library
from reading.models import LibraryText


class Command(BaseCommand):
    help = "Import the bundled texts/manifest.json library into the database (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite", action="store_true",
            help="Reset content of texts that already exist (groups and active flag are kept).",
        )

    def handle(self, *args, overwrite=False, **options):
        created = updated = skipped = 0
        for text in load_library()[1]:
            fields = dict(
                title=text.title, author=text.author, year=text.year, lang=text.lang,
                topic=text.topic, register=text.register, copyright=text.copyright,
                excerpt=text.excerpt, source=text.source, script=text.script, body=text.body,
            )
            row, was_created = LibraryText.objects.get_or_create(source_ref=text.id, defaults=fields)
            if was_created:
                created += 1
            elif overwrite:
                for name, value in fields.items():
                    setattr(row, name, value)
                row.save()
                updated += 1
            else:
                skipped += 1
        self.stdout.write(f"created={created} updated={updated} skipped={skipped}")
```
Create empty `__init__.py` in `management/` and `management/commands/`.

- [ ] **Step 6:** `makemigrations reading` (verify the generated next migration (0003 — `0002_cachedreply` already exists from the reply-cache feature) adds `LibraryText`, the `user` FK and index and **nothing destructive**), run `test reading accounts` → PASS.

- [ ] **Step 7: Checkpoint.**

---

### Task 8: `LibraryText` admin (paste or upload, group tick-boxes)

**Files:**
- Create: `APP/reading/admin.py`
- Create: `APP/reading/tests/test_admin.py`

**Interfaces:**
- Consumes: `LibraryText`, `text_from_upload`, `plain_text`, `LANG_NAMES`.
- Produces: admin for `LibraryText` with optional `upload` file filling `body` (and detecting `lang`/`script` if blank), `groups` selector, list filters.

- [ ] **Step 1: Failing tests** — `reading/tests/test_admin.py`:

```python
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from reading.models import LibraryText


class LibraryTextAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("root", "r@x.org", "pw-root-12345"))
        self.group = Group.objects.create(name="Y1")

    def test_add_by_pasting_body_and_picking_groups(self):
        response = self.client.post(reverse("admin:reading_librarytext_add"), {
            "source_ref": "de-90", "title": "T", "lang": "de", "body": "Hallo Welt.",
            "active": "on", "groups": [self.group.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(LibraryText.objects.get().groups.all()), [self.group])

    def test_add_by_uploading_a_file_fills_body(self):
        upload = SimpleUploadedFile("t.txt", "Ceci est un texte français assez long pour être détecté "
                                    "comme du français par le détecteur de langue.".encode())
        self.client.post(reverse("admin:reading_librarytext_add"), {
            "source_ref": "fr-90", "title": "T", "lang": "fr", "body": "", "upload": upload, "active": "on"})
        self.assertIn("texte français", LibraryText.objects.get(source_ref="fr-90").body)

    def test_empty_body_without_upload_is_rejected(self):
        response = self.client.post(reverse("admin:reading_librarytext_add"), {
            "source_ref": "x", "title": "T", "lang": "de", "body": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LibraryText.objects.count(), 0)

    def test_changelist_loads(self):
        self.assertEqual(self.client.get(reverse("admin:reading_librarytext_changelist")).status_code, 200)
```

- [ ] **Step 2: Run, expect FAIL** (`NoReverseMatch`).

- [ ] **Step 3: Implement** `reading/admin.py`:

```python
from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin

from .logic.corpus import plain_text, script_of
from .models import LibraryText


class LibraryTextForm(forms.ModelForm):
    upload = forms.FileField(
        required=False,
        help_text="Optional: a .txt or .md file. Its text replaces the Body box.",
    )
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 20}), required=False)

    class Meta:
        model = LibraryText
        fields = "__all__"

    def clean(self):
        data = super().clean()
        upload = data.get("upload")
        if upload:
            raw = upload.read().decode("utf-8", errors="replace")
            is_markdown = upload.name.lower().endswith((".md", ".markdown"))
            data["body"] = plain_text(raw, is_markdown)
        if not (data.get("body") or "").strip():
            self.add_error("body", "Paste the text here or upload a file.")
        elif data.get("lang") == "zh" and not data.get("script"):
            data["script"] = script_of(data["body"])
        return data


@admin.register(LibraryText)
class LibraryTextAdmin(ModelAdmin):
    form = LibraryTextForm
    list_display = ("source_ref", "title", "lang", "group_names", "active", "updated_at")
    list_filter = ("lang", "active", "groups")
    search_fields = ("source_ref", "title", "author")
    filter_horizontal = ("groups",)
    list_editable = ("active",)

    @admin.display(description="Visible to")
    def group_names(self, obj):
        names = [group.name for group in obj.groups.all()]
        return ", ".join(names) if names else "everyone"
```
`list_editable` + unfold may need `list_display_links=("source_ref",)`; add it if the changelist test errors.

- [ ] **Step 4: Run** `test reading` → PASS.

- [ ] **Step 5: Checkpoint.**

---

### Task 9: Wire views — library visibility, owner-scoped history

**Files:**
- Modify: `APP/reading/views.py`
- Create: `APP/reading/tests/test_views_auth.py`

**Interfaces:**
- Consumes: `library.load_texts`, `library.get_text` (Task 7); `AUTH_REQUIRED`; `ReadingSession.user`.
- Produces: `_owner(request) -> dict` (`{"user": user}` when `AUTH_REQUIRED` else `{"session_key": key}`); every ReadingSession query/creation goes through it.

- [ ] **Step 1: Failing tests** — `reading/tests/test_views_auth.py`:

```python
from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from reading.models import LibraryText, ReadingSession


def _text(ref, groups=()):
    t = LibraryText.objects.create(source_ref=ref, title=f"Title {ref}", lang="de", body="Hallo Welt. " * 20)
    t.groups.set(groups)
    return t


@override_settings(AUTH_REQUIRED=True, LIBRARY_SOURCE="db")
class GroupedLibraryTests(TestCase):
    def setUp(self):
        self.g1, self.g2 = Group.objects.create(name="Y1"), Group.objects.create(name="Y2")
        _text("open"); _text("y1", [self.g1]); _text("y2", [self.g2])
        self.user = User.objects.create_user("a@x.org", "a@x.org")
        self.user.groups.add(self.g1)
        self.client.force_login(self.user)

    def test_home_lists_only_permitted_texts(self):
        page = self.client.get(reverse("reading:home"))
        shown = {t.id for _, pool in page.context["groups"] for t in pool}
        self.assertEqual(shown, {"open", "y1"})

    def test_guessing_a_hidden_texts_url_is_a_404(self):
        self.assertEqual(self.client.get(reverse("reading:open", kwargs={"source_ref": "y2"})).status_code, 404)
        self.assertEqual(ReadingSession.objects.count(), 0)

    def test_permitted_text_opens_and_session_belongs_to_user(self):
        self.client.get(reverse("reading:open", kwargs={"source_ref": "y1"}))
        self.assertEqual(ReadingSession.objects.get().user, self.user)

    def test_reopening_reuses_the_users_session_across_logins(self):
        self.client.get(reverse("reading:open", kwargs={"source_ref": "y1"}))
        self.client.post(reverse("accounts:logout"))
        self.client.force_login(self.user)
        self.client.get(reverse("reading:open", kwargs={"source_ref": "y1"}))
        self.assertEqual(ReadingSession.objects.count(), 1)

    def test_other_users_cannot_read_my_session_or_history(self):
        self.client.get(reverse("reading:open", kwargs={"source_ref": "y1"}))
        mine = ReadingSession.objects.get()
        other = User.objects.create_user("b@x.org", "b@x.org"); other.groups.add(self.g1)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("reading:read", kwargs={"pk": mine.pk})).status_code, 404)
        self.assertNotContains(self.client.get(reverse("reading:history")), "Title y1")

    def test_history_survives_a_text_being_restricted_later(self):
        self.client.get(reverse("reading:open", kwargs={"source_ref": "y1"}))
        mine = ReadingSession.objects.get()
        LibraryText.objects.filter(source_ref="y1").update(active=False)
        # gone from the library and cannot be newly opened ...
        self.assertEqual(self.client.get(reverse("reading:open", kwargs={"source_ref": "y1"})).status_code, 404)
        # ... but the owner's existing history row still opens.
        self.assertEqual(self.client.get(reverse("reading:read", kwargs={"pk": mine.pk})).status_code, 302)


@override_settings(AUTH_REQUIRED=True, LIBRARY_SOURCE="db")
class UploadScopingTests(TestCase):
    def test_uploads_are_private_to_the_uploader(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        a = User.objects.create_user("a@x.org", "a@x.org"); b = User.objects.create_user("b@x.org", "b@x.org")
        self.client.force_login(a)
        self.client.post(reverse("reading:upload"), {
            "file": SimpleUploadedFile("mine.txt", ("Das ist mein eigener deutscher Text. " * 10).encode()),
            "language": "de"})
        self.client.force_login(b)
        self.assertNotContains(self.client.get(reverse("reading:history")), "mine")
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Edit `reading/views.py`.**

Replace imports `from .logic.corpus import LANG_NAMES, Text, load_library, text_from_upload` with `from .logic.corpus import LANG_NAMES, Text, text_from_upload` and add `from django.conf import settings` and `from . import library`.

Replace `_get_session` and add helpers directly under `_ensure_session_key`:

```python
def _owner(request) -> dict:
    """The ReadingSession filter identifying whose history this is."""
    if settings.AUTH_REQUIRED:
        return {"user": request.user}
    return {"session_key": _session_key(request)}


def _owner_lookup(request) -> tuple[dict, dict]:
    """(get_or_create lookup, extra defaults) for creating a ReadingSession."""
    key = _ensure_session_key(request)
    if settings.AUTH_REQUIRED:
        return {"user": request.user}, {"session_key": key}
    return {"session_key": key}, {}


def _get_session(request, pk: int) -> ReadingSession:
    return get_object_or_404(ReadingSession, pk=pk, **_owner(request))
```

`home_view`: replace `_, texts = load_library()` with `texts = library.load_texts(request.user)`; replace the history block with:

```python
    history = []
    if settings.AUTH_REQUIRED or _session_key(request):
        history = list(ReadingSession.objects.filter(**_owner(request)).order_by("-created_at"))
```

`open_view`: replace the first lines with:

```python
    text = library.get_text(source_ref, request.user)
    if text is None:
        raise Http404("Text not found.")

    lookup, extra = _owner_lookup(request)
    session, _created = ReadingSession.objects.get_or_create(
        source_ref=f"lib:{text.id}",
        **lookup,
        defaults=dict(
            **extra,
            title=text.title,
            ...  # remaining defaults unchanged
```
(remove the old `_ensure_session_key(request)` call and the `session_key=request.session.session_key` kwarg.)

`upload_view`: same pattern — remove `_ensure_session_key(request)` and the `session_key=` kwarg, use `lookup, extra = _owner_lookup(request)` and `**lookup` / `**extra` in defaults.

`history_view`: replace the `session_key = _session_key(request)` / `if session_key:` guard and the `.filter(session_key=session_key)` with `if settings.AUTH_REQUIRED or _session_key(request):` and `.filter(**_owner(request))`.

`reset_view` re-opens a library text — find its `get_or_create`/`library` usage (the lines after `session.delete()`); it calls `redirect("reading:open", source_ref=...)` which goes through `open_view`, so no change beyond the above. Verify with a grep that no other `session_key=` filter or `load_library` call remains in `views.py`: `grep -n "session_key=\|load_library" reading/views.py` → only `_session_key`/`_ensure_session_key` internals.

- [ ] **Step 4: Run** `test reading accounts` → **all PASS, including `test_baseline`** (flag off, files library, anonymous).

- [ ] **Step 5: Checkpoint.**

---

### Task 10: Copy tweaks for signed-in mode

**Files:**
- Modify: `APP/reading/templates/reading/history.html`, `home.html`
- Create: `APP/reading/tests/test_templates.py`

**Interfaces:** consumes `auth_required` context flag (Task 2).

- [ ] **Step 1: Failing test**:

```python
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


class HistoryCopyTests(TestCase):
    @override_settings(AUTH_REQUIRED=False)
    def test_anonymous_copy_mentions_browser_session(self):
        self.assertContains(self.client.get(reverse("reading:history")), "this browser")

    @override_settings(AUTH_REQUIRED=True, LIBRARY_SOURCE="db")
    def test_signed_in_copy_mentions_account(self):
        self.client.force_login(User.objects.create_user("a@x.org", "a@x.org"))
        page = self.client.get(reverse("reading:history"))
        self.assertContains(page, "your account")
        self.assertNotContains(page, "this browser")
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Edit `history.html` line 7** — replace “tied to an account — it's scoped to this browser's session only.” sentence with:

```django
{% if auth_required %}Your history is saved to your account, so it follows you across devices.{% else %}Your history is scoped to this browser's session only — it isn't tied to an account.{% endif %}
```
(read the surrounding sentence first so the paragraph still reads naturally). In `home.html`, change “No texts found in the library.” to:

```django
<p>{% if auth_required %}No texts are available to your groups yet — ask your teacher.{% else %}No texts found in the library.{% endif %}</p>
```

- [ ] **Step 4: Run** `test reading accounts` → PASS.

- [ ] **Step 5: Checkpoint.**

---

### Task 11: Packaging, env, docs, dormant deployment, verification

**Files:**
- Modify: `APP/Dockerfile`, `APP/.env.production.example`, `APP/.dockerignore` (if it excludes `accounts`)
- Modify: `/var/www/academic-reading/docs/AUTH_AND_GROUPS.md`
- Modify: `/var/www/cnlp-docker-hosting/docker-compose.yml` (only if it needs a new volume for `sent_emails`; otherwise untouched)

**Interfaces:** none new.

- [ ] **Step 1: Dockerfile** — add `COPY accounts/ ./accounts/` beside the `COPY reading/ ./reading/` line. Check `.dockerignore` does not exclude `accounts`.

- [ ] **Step 2: `.env.production.example`** — append (values blank/commented, with explanatory comments):

```
# ── Sign-in (all dormant until switched on) ──
# AUTH_REQUIRED=true needs LIBRARY_SOURCE=db and a completed import_library.
AUTH_REQUIRED=false
LIBRARY_SOURCE=files
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
# Entra redirect URI: https://cnlp.langcen.cam.ac.uk/academic-reading/auth/sso/complete/azuread-tenant-oauth2/
EMAIL_PASSWORD_LOGIN_ENABLED=false
EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend
EMAIL_HOST=
EMAIL_PORT=25
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=false
DEFAULT_FROM_EMAIL=
# Login monitor (see /var/www/login-monitor/README.md)
MONITOR_URL=
MONITOR_TOKEN=
MONITOR_APP_NAME=
```
Do **not** edit the live `.env`; the new variables all default off.

- [ ] **Step 3: Full test run** — `DATABASE_URL= ../.django-venv/bin/python manage.py test -v 2` → everything PASS; `manage.py check --deploy` reviewed (warnings acceptable only for HSTS/SSL redirect handled by Caddy).

- [ ] **Step 4: Dry-run migrations against a copy of production data** — dump the v1 DB to the scratchpad (`docker exec cnlp-mariadb-academic-reading-v1 mariadb-dump …` using credentials from the `.env`; confirm the container name with `docker ps` first), restore to a throwaway sqlite/maria instance, run `migrate`, confirm `reading` and `accounts` migrations apply with no data loss (row counts of `reading_readingsession` / `reading_activityturn` equal before/after).

- [ ] **Step 5: ⛔ STOP — ask the user for go-ahead** to rebuild/restart the live `cnlp-academic-reading` container. State: it is a live app, the release is dormant (flags off, files library), and migrations add tables only. Take a DB backup first (`mariadb-dump` into the app's backup location, confirm it is non-empty). Only then, from `/var/www/cnlp-docker-hosting`: `docker compose build academic-reading && docker compose up -d academic-reading` (the shared compose only — never the per-app compose file).

- [ ] **Step 6: Post-deploy verification (dormant)** — `curl -s -o /dev/null -w "%{http_code}" https://cnlp.langcen.cam.ac.uk/academic-reading/health/` = 200; home page returns 200 anonymously and lists 37 texts (`curl … | grep -c "text-card"` = 37); `docker exec cnlp-academic-reading python manage.py import_library` → `created=37`; `docker logs cnlp-academic-reading --tail 50` has no errors; an existing browser's history is intact.

- [ ] **Step 7: Create the first admin when the user supplies credentials** — `docker exec -it cnlp-academic-reading python manage.py createsuperuser` (or the user's chosen method); verify login at `/academic-reading/django-admin/`.

- [ ] **Step 8: Verify the DB library live before trusting it** — with `LIBRARY_SOURCE=files` still set, compare `LibraryText` count/titles to the home page; then (user-approved) set `LIBRARY_SOURCE=db` in the live `.env`, restart via the shared compose, and confirm the home page still lists the same 37 texts. Leave `AUTH_REQUIRED=false`.

- [ ] **Step 9: Docs** — rewrite `/var/www/academic-reading/docs/AUTH_AND_GROUPS.md`: status table (v1 built/deployed dormant), deviations list (above), env var reference, admin how-to (add group → add allowlist entry → add/upload text → tick groups → create email user), the exact **switch-over runbook** (set Entra creds, `LIBRARY_SOURCE=db` verified, create groups/allowlist entries/admin, set `AUTH_REQUIRED=true`, restart, smoke test: allowlisted account sees restricted text, non-allowlisted refused, anonymous redirected), the **rollback** (set `AUTH_REQUIRED=false`, restart), and the note that anonymous history is unreachable once auth is on. Add the Build log entries from each checkpoint. Update the README if one exists for v1 (none today — skip).

- [ ] **Step 10: Checkpoint + hand back** — summarize to the user: what's live (dormant), what they must supply for switch-over (Entra client id/secret, admin login, SMTP when wanted), and that the **v2 plan** is next.

---

## Self-review (done at plan time)

- **Spec coverage:** R1 → scope note + Task 11 hand-back; R2 → Tasks 3–5; R3 → Tasks 3,4,7 (union tests); R4 → Tasks 2, 11 (flags, dormant baseline); R5 → Tasks 2, 11 (env, hidden button); R6 → Tasks 7–8 (admin-only text management); R7 → Tasks 5–6 (login form, throttle, email, flag); R8 → Task 7 (no groups ⇒ open); R9 → Task 11 step 9 + checkpoints; R10 → Task 11 step 7. Spec §4.5 history → Tasks 7, 9; §4.7 deployment → Task 11. Login-monitor open item → resolved: copy `report_login` (Task 4) + env vars (Task 11).
- **Placeholders:** none intended; places that say “verify against installed version” (unfold admin forms, Django password-confirm redirect chain) give the concrete fallback.
- **Type consistency:** `load_texts(user)`, `get_text(ref, user)`, `_owner(request)`, `_owner_lookup(request)`, `AllowedLogin.matches(email)`, `allowed_entries` (list of pks) are used identically across tasks 3–9.
- **Known limits carried into the build log:** throttle is per-process; anonymous history is orphaned at switch-over; `LIBRARY_SOURCE=files` is refused with `AUTH_REQUIRED=true`.
