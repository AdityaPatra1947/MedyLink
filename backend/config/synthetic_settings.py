"""Dedicated synthetic-data environment; never an application deployment default.

Set SYNTHETIC_DATABASE_URL to an empty PostgreSQL database named synthetic_...,
then explicitly select --settings=config.synthetic_settings. The normal database
URL is never a fallback. Use a direct connection for migrations and this import.
"""

import os
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

_synthetic_url = os.environ.get("SYNTHETIC_DATABASE_URL", "").strip()
try:
    _parts = urlsplit(_synthetic_url)
    _database_name = unquote(_parts.path.removeprefix("/"))
    _query = parse_qsl(_parts.query, keep_blank_values=True)
    _valid_target = (
        _parts.scheme in {"postgres", "postgresql"}
        and bool(_parts.hostname)
        and re.fullmatch(r"synthetic_[A-Za-z0-9_]+", _database_name)
        and not _parts.fragment
        and len(dict(_query)) == len(_query)
        and all(
            (key == "sslmode" and value in {"require", "verify-ca", "verify-full"})
            or (key == "channel_binding" and value in {"require", "prefer", "disable"})
            for key, value in _query
        )
    )
except ValueError:
    _valid_target = False
if not _valid_target:
    raise ImproperlyConfigured(
        "Set SYNTHETIC_DATABASE_URL explicitly to a PostgreSQL database named "
        "synthetic_...; only TLS query parameters are accepted. No normal database fallback is allowed."
    )

# Override before base settings load_dotenv (which does not overwrite env vars).
os.environ["DATABASE_URL"] = _synthetic_url
from .settings import *  # noqa: E402,F403

if not DEBUG:  # noqa: F405
    raise ImproperlyConfigured("Synthetic settings require DJANGO_DEBUG=true.")

SYNTHETIC_IMPORT_ALLOWED = True
SYNTHETIC_IMPORT_DATABASE_NAME = _database_name
# A direct TLS connection is required even in the dedicated development database.
DATABASES["default"].setdefault("OPTIONS", {}).setdefault("sslmode", "require")  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PRIVATE_MEDIA_ROOT = BASE_DIR.parent / ".local" / "synthetic" / "private-media"  # noqa: F405
MEDIA_ROOT = PRIVATE_MEDIA_ROOT

# Cookies are scoped to a hostname, not a port. Keep the local demo session
# separate from the normal application when both run on localhost.
AUTH_ACCESS_COOKIE_NAME = "medylink_synthetic_access_token"
AUTH_REFRESH_COOKIE_NAME = "medylink_synthetic_refresh_token"
CSRF_COOKIE_NAME = "medylink_synthetic_csrftoken"
SESSION_COOKIE_NAME = "medylink_synthetic_sessionid"

# Explicit, deterministic demo features; never enabled by normal application settings.
SYNTHETIC_REPORT_EXTRACTION_ALLOWED = True
SYNTHETIC_REPORT_SCORE_ENABLED = True
