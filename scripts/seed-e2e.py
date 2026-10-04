"""Create fresh synthetic browser-test identities, only in the isolated E2E database."""

import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.e2e_settings"
import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from clinic.models import ProviderApplication

expected = (ROOT / ".local" / "e2e.sqlite3").resolve()
if (
    not getattr(settings, "E2E_TEST_MODE", False)
    or Path(settings.DATABASES["default"]["NAME"]).resolve() != expected
):
    raise SystemExit(
        "Refusing to seed anything except the isolated browser-test database."
    )

call_command("migrate", interactive=False, verbosity=0)
run_id = uuid.uuid4().hex[:10]
password = "SyntheticBrowserOnly!2026-" + run_id
fixture = {
    "run_id": run_id,
    "password": password,
    "accounts": {},
}
with transaction.atomic():
    for key, role, name in [
        ("patient", "patient", "Test Patient"),
        ("doctor", "doctor", "Test Doctor"),
        ("second_doctor", "doctor", "Other Doctor"),
        ("pharmacist", "pharmacist", "Test Pharmacist"),
        ("admin", "admin", "Test Reviewer"),
    ]:
        email = f"{key}-{run_id}@example.test"
        user = get_user_model().objects.create_user(
            email,
            password,
            name=name + " " + run_id,
            role=role,
            email_verified_at=timezone.now(),
            storage_consent_at=timezone.now(),
            privacy_version="1.0",
        )
        fixture["accounts"][key] = {
            "email": email,
            "id": str(user.id),
            "name": user.name,
            "account_id": user.account_id,
        }
        if role in ("doctor", "pharmacist"):
            ProviderApplication.objects.create(
                provider=user,
                version=1,
                status="approved",
                registration_number="E2E-" + str(user.id),
                registering_body="SYNTHETIC TEST COUNCIL",
                practice_address="Synthetic test address",
                specialty="Test practice",
                shop_name="Test Pharmacy " + run_id if role == "pharmacist" else "",
                shop_license="TEST-" + run_id if role == "pharmacist" else "",
                shop_license_expires=timezone.localdate() + timedelta(days=365),
                valid_until=timezone.now() + timedelta(days=30),
                reason="Synthetic test fixture; never production verification",
                evidence_reviewed="Synthetic fixture",
            )

# An existing unverified account exercises the standalone request-code flow.
pending = get_user_model().objects.create_user(
    f"pending-email-{run_id}@example.test",
    password,
    name="Synthetic pending verification",
    role="patient",
    storage_consent_at=timezone.now(),
    privacy_version="1.0",
)
fixture["pending_email"] = pending.email

destination = ROOT / ".local" / "e2e-fixture.json"
destination.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
print(
    "Synthetic browser fixture created at .local/e2e-fixture.json in isolated SQLite database."
)
