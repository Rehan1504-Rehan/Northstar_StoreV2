"""Django settings for the ecommerce project.

The project deliberately keeps configuration in one beginner-friendly file. In
production, all sensitive values come from environment variables.
"""
from pathlib import Path
from urllib.parse import urlsplit
import os
import secrets
import warnings

import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# Environment values are easy to fill in slightly wrongly: people paste a full
# URL where a hostname is expected, wrap the value in quotes, or copy the
# markdown form of a variable straight out of a chat message
# (``ALLOWED_HOSTS=[my-app.onrender.com]``). Django compares the Host header to
# ALLOWED_HOSTS literally, so any decoration like that makes every request fail
# with a bare "400 Bad Request" and no clue as to why.
#
# Rather than hoping every dashboard value is pristine, normalise what we read:
# a stray bracket or quote then degrades to a working site instead of an
# unexplained outage.
_DECORATION_PAIRS = (('"', '"'), ("'", "'"), ("[", "]"), ("(", ")"), ("<", ">"))
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"}

# Variables the hosting platform sets by itself. Render injects
# RENDER_EXTERNAL_HOSTNAME/RENDER_EXTERNAL_URL; Railway injects the RAILWAY_*
# pair; Heroku injects HEROKU_APP_DOMAIN. Reading them means a correct deploy
# does not depend on someone typing the hostname into the dashboard.
_PLATFORM_HOST_VARIABLES = (
    "RENDER_EXTERNAL_HOSTNAME",
    "RENDER_EXTERNAL_URL",
    "RAILWAY_PUBLIC_DOMAIN",
    "RAILWAY_STATIC_URL",
    "HEROKU_APP_DOMAIN",
)


def clean_env_value(value: str) -> str:
    """Strip whitespace, matching quotes, and matching brackets from a value."""
    cleaned = value.strip()
    while len(cleaned) > 1:
        for opening, closing in _DECORATION_PAIRS:
            if cleaned.startswith(opening) and cleaned.endswith(closing):
                cleaned = cleaned[1:-1].strip()
                break
        else:
            return cleaned
    return cleaned


def env(name: str, default: str = "") -> str:
    """Read an environment variable and clean it up."""
    return clean_env_value(os.getenv(name, default))


def env_bool(name: str, default: bool = False) -> bool:
    """Read a conventional true/false environment variable."""
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def csv_env(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable into a clean list."""
    return [value for value in (clean_env_value(part) for part in env(name, default).split(",")) if value]


def bare_host(value: str) -> str:
    """Reduce anything host-like to the bare hostname Django matches on.

    Accepts ``my-app.onrender.com``, ``https://my-app.onrender.com/``,
    ``my-app.onrender.com:443`` and ``user:pass@my-app.onrender.com`` alike.
    """
    host = clean_env_value(value)
    if "://" in host:
        host = urlsplit(host).hostname or ""
    host = host.split("/")[0].split("?")[0].split("#")[0]
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    host = host.strip().rstrip(".").lower()
    # Django strips the port before matching, so drop it here too.
    if host.count(":") == 1 and host.rsplit(":", 1)[1].isdigit():
        host = host.rsplit(":", 1)[0]
    return host


def platform_hostnames() -> list[str]:
    """Hostnames published by the hosting platform itself, if any."""
    hosts: list[str] = []
    for variable in _PLATFORM_HOST_VARIABLES:
        host = bare_host(env(variable))
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def build_allowed_hosts(debug: bool) -> list[str]:
    """Build ALLOWED_HOSTS from the environment plus platform metadata."""
    hosts = [host for host in (bare_host(value) for value in csv_env("ALLOWED_HOSTS")) if host]

    # Always accept the hostname the platform advertises for this service: it
    # is authoritative, and it keeps the site reachable when ALLOWED_HOSTS is
    # missing, stale, or names a different service.
    for host in platform_hostnames():
        if host not in hosts:
            hosts.append(host)

    if not hosts and debug:
        # A permissive list keeps local work usable through a dev tunnel or
        # preview host. Production never falls back to this.
        return ["localhost", "127.0.0.1", "[::1]", "testserver", "*"]
    return hosts


def _csrf_origin(value: str, debug: bool) -> str:
    """Return a CSRF_TRUSTED_ORIGINS entry, adding a scheme when it is missing."""
    origin = clean_env_value(value).rstrip("/")
    if not origin:
        return ""
    if origin.startswith("//"):
        return f"{'http' if debug else 'https'}:{origin}"
    if "://" not in origin:
        scheme = "http" if bare_host(origin) in _LOCAL_HOSTNAMES else ("http" if debug else "https")
        return f"{scheme}://{origin}"
    return origin


def build_csrf_trusted_origins(debug: bool) -> list[str]:
    """Build CSRF_TRUSTED_ORIGINS from the environment plus platform metadata.

    Django requires a scheme (``https://my-app.onrender.com``) and rejects a
    bare hostname, so add the missing scheme instead of failing every form post
    with "CSRF verification failed".
    """
    origins = [origin for origin in (_csrf_origin(value, debug) for value in csv_env("CSRF_TRUSTED_ORIGINS")) if origin]
    for host in platform_hostnames():
        origin = f"https://{host}"
        if origin not in origins:
            origins.append(origin)
    return origins


DEBUG = env_bool("DEBUG", True)
# A random development key keeps a brand-new checkout easy to run without
# placing a reusable secret in Git. Production must provide its own key.
SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = secrets.token_urlsafe(50)
    else:
        raise ImproperlyConfigured("Set SECRET_KEY in the production environment.")


# In local DEBUG mode, a missing value falls back to a permissive list so the
# app is usable through a dev tunnel or preview host. Production must set an
# explicit comma-separated ALLOWED_HOSTS value; the hostname the hosting
# platform advertises is added automatically either way.
ALLOWED_HOSTS = build_allowed_hosts(DEBUG)
CSRF_TRUSTED_ORIGINS = build_csrf_trusted_origins(DEBUG)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "store.apps.StoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ecommerce.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.cart_context",
                "store.context_processors.storefront_context",
            ],
        },
    },
]

WSGI_APPLICATION = "ecommerce.wsgi.application"
ASGI_APPLICATION = "ecommerce.asgi.application"

# SQLite is convenient for local work. Render and Railway supply DATABASE_URL
# for PostgreSQL, which dj-database-url parses for us. The URL is cleaned first
# so a value pasted with surrounding quotes still connects.
database_url = env("DATABASE_URL")
DATABASES = {
    "default": dj_database_url.parse(database_url, conn_max_age=600, conn_health_checks=True)
    if database_url
    else dj_database_url.parse(
        f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", str(BASE_DIR / "media")))

# Where uploaded product images are kept.
#   "database"   - (default) bytes are stored in the database next to the
#                  products. Cloud container filesystems are wiped on every
#                  deploy and restart, so anything written to MEDIA_ROOT is
#                  lost; the database is the one place that already persists.
#   "filesystem" - classic MEDIA_ROOT storage. Only choose this when MEDIA_ROOT
#                  points at a real persistent disk/volume mount.
MEDIA_STORAGE = os.getenv("MEDIA_STORAGE", "database").strip().lower()
if MEDIA_STORAGE not in {"database", "filesystem"}:
    raise ImproperlyConfigured("MEDIA_STORAGE must be either 'database' or 'filesystem'.")

_DEFAULT_FILE_BACKEND = (
    "store.storage.DatabaseStorage"
    if MEDIA_STORAGE == "database"
    else "django.core.files.storage.FileSystemStorage"
)

# Django 5.1 removed DEFAULT_FILE_STORAGE/STATICFILES_STORAGE in favour of the
# STORAGES dict, so the old settings were being ignored. Both aliases must be
# listed here: this dict replaces the defaults instead of merging with them.
# The staticfiles backend compresses collected assets without hashing their
# names, so a deployment that skips `collectstatic` degrades gracefully rather
# than raising "Missing staticfiles manifest entry" on every page.
STORAGES = {
    "default": {"BACKEND": _DEFAULT_FILE_BACKEND},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Set SERVE_MEDIA=False only when an external CDN/object store answers
# /media/ directly. Otherwise Django serves uploads itself, reading them from
# the database (or MEDIA_ROOT when MEDIA_STORAGE=filesystem).
SERVE_MEDIA = env_bool("SERVE_MEDIA", True)
# How long browsers may cache an uploaded image before revalidating (ETag).
MEDIA_CACHE_SECONDS = int(os.getenv("MEDIA_CACHE_SECONDS", "3600"))
# Uploads are held in memory and stored in a database row, so cap their size.
MAX_IMAGE_UPLOAD_MB = float(os.getenv("MAX_IMAGE_UPLOAD_MB", "5"))
MAX_IMAGE_UPLOAD_BYTES = int(MAX_IMAGE_UPLOAD_MB * 1024 * 1024)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Apply pending migrations when the web server boots, so a deployment whose
# build step does not run `manage.py migrate` still works. See
# ecommerce/startup.py. Set False if migrations are handled by the platform.
RUN_STARTUP_TASKS = env_bool("RUN_STARTUP_TASKS", True)

LOGIN_URL = "store:login"
LOGIN_REDIRECT_URL = "store:home"
LOGOUT_REDIRECT_URL = "store:home"

# Optional ISO-8601 deadlines for homepage promotional timers. Left blank by
# default so the storefront never displays a fake or resetting countdown.
FLASH_DEAL_DEADLINE = env("FLASH_DEAL_DEADLINE", "")
SPECIAL_OFFER_DEADLINE = env("SPECIAL_OFFER_DEADLINE", "")

# These settings are safe for local development and become useful when the
# Railway service is configured to terminate HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# A permissive ALLOWED_HOSTS is easy to set and hard to notice; warn about it
# in the deploy log, since the site would answer every hostname.
if ALLOWED_HOSTS == ["*"] and not DEBUG:
    warnings.warn(
        "ALLOWED_HOSTS is '*': every hostname is accepted. List your public "
        "hostname instead, for example ALLOWED_HOSTS=northstar-storev2.onrender.com.",
        stacklevel=2,
    )
