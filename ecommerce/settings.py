"""Django settings for the ecommerce project.

The project deliberately keeps configuration in one beginner-friendly file. In
production, all sensitive values come from environment variables.
"""
from pathlib import Path
import os
import secrets

import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """Read a conventional true/false environment variable."""
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DEBUG", True)
# A random development key keeps a brand-new checkout easy to run without
# placing a reusable secret in Git. Production must provide its own key.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = secrets.token_urlsafe(50)
    else:
        raise ImproperlyConfigured("Set SECRET_KEY in the production environment.")


def csv_env(name: str, default: str = "") -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


# In local DEBUG mode, ``*`` makes the app usable through a dev tunnel or
# Arena preview host. Production never uses this fallback: set an explicit
# comma-separated ALLOWED_HOSTS value there.
if "ALLOWED_HOSTS" in os.environ:
    ALLOWED_HOSTS = csv_env("ALLOWED_HOSTS")
elif DEBUG:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver", "*"]
else:
    ALLOWED_HOSTS = []
CSRF_TRUSTED_ORIGINS = csv_env("CSRF_TRUSTED_ORIGINS")

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

# SQLite is convenient for local work. Railway supplies DATABASE_URL for
# PostgreSQL, which dj-database-url parses for us.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}",
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

# Tell Django's checks (and people reading the deployment) which host setting
# applies when DEBUG=False. A missing production value should be fixed rather
# than silently accepting every host.
if not DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = []
