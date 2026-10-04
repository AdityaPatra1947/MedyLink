"""Fast isolated tests; use TEST_DATABASE_URL for PostgreSQL concurrency coverage."""

import os

os.environ["DJANGO_TESTING"] = "true"
from .settings import *  # noqa: F403,E402

SECRET_KEY = "test-only-django-secret-not-used-outside-tests" * 2
JWT_SIGNING_KEY = "test-only-jwt-secret-not-used-outside-tests" * 2
SIMPLE_JWT = {**SIMPLE_JWT, "SIGNING_KEY": JWT_SIGNING_KEY}  # noqa: F405
DEBUG = True
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
SECURE_SSL_REDIRECT = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
if os.getenv("TEST_DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["TEST_DATABASE_URL"], conn_max_age=0
        )
    }  # noqa: F405
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
else:
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    }
