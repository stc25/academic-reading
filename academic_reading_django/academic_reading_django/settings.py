"""Django settings for the academic_reading_django project.

No accounts, no admin — every reader is anonymous and scoped to their Django
session cookie. The reading logic itself (corpus/prompts/annotate/languages/
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

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "django.contrib.messages",
    "reading.apps.ReadingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
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
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365  # a year — this is a no-login history feature

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = os.getenv("STATIC_URL", (f"{PUBLIC_PATH}static/") if PUBLIC_PATH else "/static/")
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("APP_LOG_LEVEL", "INFO")},
}
