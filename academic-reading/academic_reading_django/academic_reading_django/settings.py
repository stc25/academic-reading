"""Django settings for the academic_reading_django project.

Sign-in is mandatory (Entra SSO or admin-created email accounts): history belongs to
the reader's account and library texts are shown according to the reader's groups. The reading logic itself (corpus/prompts/annotate/languages/
llm) lives in reading/logic/, ported from the original Streamlit app's lib/
package.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS") or os.getenv("ALLOWED_HOSTS", "*")
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS.split(",") if host.strip()]

_csrf_origins = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").strip()
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]

# Subpath under which the app is served. Caddy terminates TLS, then
# `handle_path /academic-reading/*` strips the prefix before proxying, so
# the app itself sees root-relative paths. To make generated URLs (redirects,
# links, static) carry the prefix back to the browser, derive Django's
# FORCE_SCRIPT_NAME and STATIC_URL from whichever subpath env var is present.
public_path = os.getenv("PUBLIC_PATH", "").strip()
force_script_name = os.getenv("FORCE_SCRIPT_NAME", "").strip()
if not public_path and force_script_name:
    public_path = force_script_name

if public_path and public_path != "/":
    PUBLIC_PATH = f"/{public_path.strip('/')}/"
    FORCE_SCRIPT_NAME = PUBLIC_PATH.rstrip("/")
else:
    PUBLIC_PATH = ""
    FORCE_SCRIPT_NAME = force_script_name or None

def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes", "on")


# ── Feature switches ─────────────────────────────────────────────────────────
EMAIL_PASSWORD_LOGIN_ENABLED = _flag("EMAIL_PASSWORD_LOGIN_ENABLED")
# Where the library comes from: "db" (LibraryText rows, group-aware) or "files" (the bundled files,
# every text ungrouped). Fallback only; see docs/LOGIN.md.
LIBRARY_SOURCE = os.getenv("LIBRARY_SOURCE", "db").strip().lower()

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

ROOT_URLCONF = "academic_reading_django.urls"
WSGI_APPLICATION = "academic_reading_django.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "django.contrib.auth.context_processors.auth",
                "accounts.context_processors.auth_flags",
            ],
        },
    },
]

# ── Database ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "mariadb",
            "PORT": parsed.port or 3306,
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ── Sessions / static ────────────────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
# Several separate Django apps share the cnlp.langcen.cam.ac.uk domain behind
# one Caddy instance, each at its own subpath. Without an app-specific cookie
# name/path, logging into one app's session would silently overwrite another
# app's identically-named cookie in the browser. (Distinct from the sibling
# academic-reading-eng app's "are_*" cookies, even though Path scoping alone
# would already keep the two apart.)
SESSION_COOKIE_NAME = "arm_sessionid"
CSRF_COOKIE_NAME = "arm_csrftoken"
SESSION_COOKIE_PATH = PUBLIC_PATH or "/"
CSRF_COOKIE_PATH = PUBLIC_PATH or "/"
# A reader with no history yet should not be forced to accept a cookie before
# they've done anything — but everything after the first Generate/Submit
# needs the session to persist, so keep the default (cookie set on first use)
# rather than SESSION_SAVE_EVERY_REQUEST.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365  # a year — a long-lived history cookie

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = os.getenv("STATIC_URL", (f"{PUBLIC_PATH}static/") if PUBLIC_PATH else "/static/")
STATIC_ROOT = BASE_DIR / "staticfiles"

import sys

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            # The manifest storage raises on {% static %} when nothing is collected.
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if "test" in sys.argv
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("APP_LOG_LEVEL", "INFO")},
}


# ── University Microsoft sign-in (Entra ID) ─────────────────────────────────
# The sign-in button stays hidden until both KEY and SECRET are set.
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
    "accounts.pipeline.finish_login",
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

# Behind a TLS-terminating proxy: trust its scheme so absolute URLs (the SSO
# redirect URI, emailed links) are https.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ── Email (account-created / set-password emails; dormant until enabled) ────
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.filebased.EmailBackend")
EMAIL_FILE_PATH = os.getenv("EMAIL_FILE_PATH", str(BASE_DIR / "sent_emails"))
if EMAIL_BACKEND.endswith("filebased.EmailBackend"):
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
    "SITE_SUBHEADER": "Users and sign-in",
    "SITE_URL": PUBLIC_PATH or "/",
}
