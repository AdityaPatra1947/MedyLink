"""Exercise production system checks with synthetic settings, without database access."""

import os
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
os.environ.update(
    {
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_DEBUG": "false",
        "DJANGO_TESTING": "false",
        "DJANGO_SECRET_KEY": secrets.token_hex(48),
        "JWT_SIGNING_KEY": secrets.token_hex(48),
        "DATABASE_URL": "postgresql://test:test@localhost/synthetic?sslmode=require",
        "REDIS_URL": "redis://localhost:6379/0",
        "DJANGO_ALLOWED_HOSTS": "health.example.test",
        "FRONTEND_ORIGIN": "https://health.example.test",
        "CSRF_TRUSTED_ORIGINS": "https://health.example.test",
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": "smtp.example.test",
        "EMAIL_HOST_USER": "test",
        "EMAIL_HOST_PASSWORD": "test",
        "DEFAULT_FROM_EMAIL": "noreply@example.test",
        "PRIVATE_MEDIA_ROOT": str(root / ".local" / "production-check-evidence"),
    }
)
import django

django.setup()
from django.core.management import call_command

call_command("check", deploy=True, fail_level="WARNING")
print(
    "Production configuration checks passed with synthetic secrets. No deployment, SMTP or database connection was tested."
)
