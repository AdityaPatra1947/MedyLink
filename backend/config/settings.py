"""One Django API, backed by Neon PostgreSQL. Secrets live in backend/.env."""

import json
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
TESTING = os.getenv("DJANGO_TESTING", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
JWT_SIGNING_KEY = os.getenv("JWT_SIGNING_KEY", "")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")
ALLOWED_HOSTS = [
    x.strip()
    for x in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend").split(",")
    if x.strip()
]
CSRF_TRUSTED_ORIGINS = [
    x.strip()
    for x in os.getenv("CSRF_TRUSTED_ORIGINS", FRONTEND_ORIGIN).split(",")
    if x.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "accounts.apps.AccountsConfig",
    "clinic.apps.ClinicConfig",
    "analytics.apps.AnalyticsConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.PrivateResponseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.EnforceCSRFMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

database_url = os.getenv("DATABASE_URL", "").strip()
if database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            database_url, conn_max_age=0, conn_health_checks=True
        )
    }
    if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        raise ImproperlyConfigured("DATABASE_URL must use PostgreSQL (Neon).")
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
    DATABASES["default"].setdefault("OPTIONS", {}).update({"connect_timeout": 10})
    if ".neon.tech" in DATABASES["default"].get("HOST", ""):
        DATABASES["default"]["OPTIONS"]["sslmode"] = "require"
else:
    # A dummy backend lets the frontend and liveness endpoint start without silently
    # putting patient data in another database. Readiness explains missing setup.
    DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ["name", "email"]},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
AUTH_COOKIE_SECURE = not DEBUG
AUTH_ACCESS_COOKIE_NAME = "access_token"
AUTH_REFRESH_COOKIE_NAME = "refresh_token"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "config.middleware.csrf_failure"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
# Only run behind the supplied trusted proxy in production; do not expose backend.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "USER_ID_FIELD": "id",
    "UPDATE_LAST_LOGIN": False,
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.CookieJWTAuthentication"
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["config.throttling.SharedRateThrottle"],
    "EXCEPTION_HANDLER": "config.errors.api_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
redis_url = os.getenv("REDIS_URL", "").strip()
CACHES = {
    "default": (
        {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": redis_url,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "SOCKET_CONNECT_TIMEOUT": 3,
                "SOCKET_TIMEOUT": 3,
            },
        }
        if redis_url
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    )
}
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "MedyLink <noreply@example.com>"
)
PRIVATE_MEDIA_ROOT = Path(
    os.getenv("PRIVATE_MEDIA_ROOT") or str(BASE_DIR / "private-media")
)
MEDIA_ROOT = PRIVATE_MEDIA_ROOT
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 6
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

if not DEBUG and not TESTING:
    required = {
        "DJANGO_SECRET_KEY": SECRET_KEY,
        "JWT_SIGNING_KEY": JWT_SIGNING_KEY,
        "DATABASE_URL": database_url,
        "REDIS_URL": redis_url,
        "EMAIL_HOST": EMAIL_HOST,
        "EMAIL_HOST_USER": EMAIL_HOST_USER,
        "EMAIL_HOST_PASSWORD": EMAIL_HOST_PASSWORD,
        "PRIVATE_MEDIA_ROOT": os.getenv("PRIVATE_MEDIA_ROOT"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ImproperlyConfigured("Missing production settings: " + ", ".join(missing))
    if (
        len(SECRET_KEY) < 50
        or len(JWT_SIGNING_KEY) < 50
        or SECRET_KEY == JWT_SIGNING_KEY
    ):
        raise ImproperlyConfigured(
            "Use distinct random Django and JWT secrets of at least 50 characters."
        )
    if (
        EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend"
        or "example.com" in DEFAULT_FROM_EMAIL
    ):
        raise ImproperlyConfigured(
            "Production requires SMTP delivery and a real DEFAULT_FROM_EMAIL."
        )
    if not FRONTEND_ORIGIN.startswith("https://") or "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "Production requires HTTPS and explicit allowed hosts."
        )
    if DATABASES["default"].get("OPTIONS", {}).get("sslmode") not in {
        "require",
        "verify-full",
        "verify-ca",
    }:
        raise ImproperlyConfigured("Production database connections require TLS.")


# Clinical scoring is disabled until the operator supplies a reviewed, versioned
# policy. Malformed configuration remains unavailable rather than inventing values.
try:
    HEALTH_SCORE_POLICY = json.loads(os.getenv("HEALTH_SCORE_POLICY_JSON", "null"))
except (ValueError, TypeError):
    HEALTH_SCORE_POLICY = None
HEALTH_ALERTS_PROVIDER = os.getenv("HEALTH_ALERTS_PROVIDER", "").strip()
