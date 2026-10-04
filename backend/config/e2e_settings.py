"""Explicit isolated browser-test configuration. Never use for application deployment."""

from pathlib import Path

from .test_settings import *  # noqa: F403

E2E_TEST_MODE = True
E2E_ROOT = Path(__file__).resolve().parents[2] / ".local"
E2E_ROOT.mkdir(exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": E2E_ROOT / "e2e.sqlite3",
        "OPTIONS": {"timeout": 30, "transaction_mode": "IMMEDIATE"},
    }
}
FRONTEND_ORIGIN = "http://127.0.0.1:3001"
CSRF_TRUSTED_ORIGINS = [FRONTEND_ORIGIN]
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
AUTH_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = E2E_ROOT / "test-emails"
PRIVATE_MEDIA_ROOT = E2E_ROOT / "test-evidence"
MEDIA_ROOT = PRIVATE_MEDIA_ROOT
