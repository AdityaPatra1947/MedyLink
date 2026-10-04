"""Explicit synthetic accounts for local development, with normal auth controls."""

import json
import os
import secrets
from datetime import date
from pathlib import Path

from clinic.models import Patient
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import SecurityEvent, User

DEMO_USERS = (
    ("patient", "patient.demo@medylink.test", "Demo Patient"),
    ("doctor", "doctor.demo@medylink.test", "Demo Doctor"),
)
# Never duplicate or reset legacy demo accounts during a branding change.
LEGACY_DEMO_EMAILS = {
    "patient.demo@medylink.test": "patient.demo@arogyatrack.test",
    "doctor.demo@medylink.test": "doctor.demo@arogyatrack.test",
}
DEMO_EVENT = "synthetic_demo_account_created"


class Command(BaseCommand):
    help = (
        "Create two synthetic development accounts and save random credentials locally. "
        "Requires DEBUG. Doctor professional verification remains required."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(settings.BASE_DIR.parent / ".local" / "demo-credentials.json"),
            help="New credentials file inside the repository's ignored .local directory.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Synthetic demo accounts require DJANGO_DEBUG=true.")

        local_dir = settings.BASE_DIR.parent.resolve() / ".local"
        output = Path(options["output"]).expanduser().resolve()
        if not output.is_relative_to(local_dir) or output == local_dir:
            raise CommandError(
                "Credentials must be saved inside the repository's .local directory."
            )

        existing = {
            user.email.lower(): user
            for user in User.objects.filter(email__in=[
                *[item[1] for item in DEMO_USERS], *LEGACY_DEMO_EMAILS.values(),
            ])
        }
        if existing or output.exists():
            self.check_existing(existing, output)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Demo accounts already exist; credentials unchanged: {output}"
                )
            )
            return

        output.parent.mkdir(parents=True, exist_ok=True)
        created_file = False
        credentials = {
            "url": settings.FRONTEND_ORIGIN + "/login",
            "synthetic_demo_accounts": True,
            "notes": (
                "Synthetic email addresses are preverified for local testing. "
                "No professional application, approval, clinical records, or patient access is created."
            ),
        }
        try:
            # Exclusive creation prevents replacing an earlier credentials file.
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created_file = True
            with os.fdopen(descriptor, "w", encoding="utf-8") as credential_file:
                with transaction.atomic():
                    for role, email, name in DEMO_USERS:
                        password = secrets.token_urlsafe(24)
                        validate_password(password, User(email=email, name=name))
                        user = User.objects.create_user(
                            email=email,
                            password=password,
                            name=name,
                            role=role,
                            # Reserved .test addresses do not belong to real people.
                            email_verified_at=timezone.now(),
                            storage_consent_at=timezone.now(),
                            privacy_version="1.0",
                        )
                        if role == User.Role.PATIENT:
                            Patient.objects.create(
                                user=user, date_of_birth=date(1990, 1, 1)
                            )
                        SecurityEvent.objects.create(
                            user=user,
                            event=DEMO_EVENT,
                            metadata={
                                "synthetic": True,
                                "email_preverified_for_demo": True,
                            },
                        )
                        credentials[role] = {"email": email, "password": password}
                    json.dump(credentials, credential_file, indent=2)
                    credential_file.write("\n")
                    credential_file.flush()
                    os.fsync(credential_file.fileno())
        except Exception:
            if created_file:
                output.unlink(missing_ok=True)
            raise

        self.stdout.write(
            self.style.SUCCESS(
                f"Created synthetic patient and doctor. Credentials: {output}"
            )
        )
        self.stdout.write(
            "Doctor must complete professional review before accessing clinical features."
        )

    def check_existing(self, existing, output):
        """Be idempotent only for our accounts, and never reset an existing password."""
        try:
            credentials = json.loads(output.read_text(encoding="utf-8"))
            for role, email, name in DEMO_USERS:
                candidates = [existing[address] for address in (email, LEGACY_DEMO_EMAILS[email]) if address in existing]
                user = candidates[0] if len(candidates) == 1 else None
                saved = credentials[role]
                if (
                    user is None
                    or user.role != role
                    or user.name != name
                    or user.is_staff
                    or user.is_superuser
                    or not user.is_active
                    or saved["email"] != user.email
                    or not user.check_password(saved["password"])
                    or not SecurityEvent.objects.filter(
                        user=user, event=DEMO_EVENT
                    ).exists()
                ):
                    raise ValueError("Existing account does not match this demo setup.")
        except (OSError, ValueError, KeyError, TypeError):
            raise CommandError(
                "Demo accounts or the credentials file already exist and cannot be safely reused. "
                "Nothing was changed; review existing accounts and use normal password recovery."
            ) from None
