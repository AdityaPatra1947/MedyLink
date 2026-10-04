"""The importer never uses configured development/production data in these tests."""

import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.identifiers import ACCOUNT_ID_PREFIXES
from accounts.models import AuthSession, SecurityEvent, User
from clinic.management.commands.import_synthetic_dataset import Command
from clinic.models import (
    ClinicalEntry, DoctorPatient, LabResult, MedicalRecord, MedicationAdherenceLog,
    Patient, Prescription, PrescriptionItem, ProviderApplication,
)


def fixture():
    created = "2025-01-01T00:00:00+00:00"
    visit = "2026-09-15T10:00:00+00:00"
    users = [
        ("DOC001", "doctor", "Synthetic Doctor"),
        ("PHARM001", "pharmacist", "Synthetic Pharmacist"),
        ("ADMIN001", "admin", "Synthetic Reviewer"),
        ("PAT0001", "patient", "Synthetic Patient One"),
        ("PAT0002", "patient", "Synthetic Patient Two"),
    ]
    identities = {
        sid: {"email": f"{sid.lower()}@synthetic.arogyatrack.test", "name": name,
              "role": role, "created_at": created}
        for sid, role, name in users
    }
    providers = []
    for sid, role, _ in users[:3]:
        row = {"source_id": sid, "user": identities[sid]}
        if role != "admin":
            row["application"] = {
                "registration_number": "TEST-" + sid, "registering_body": "SYNTHETIC COUNCIL",
                "specialty": "Synthetic practice", "qualification": "Synthetic qualification",
                "practice_address": "Synthetic station area", "valid_until": "2027-09-30T00:00:00+00:00",
                "reason": "Synthetic fixture", "evidence_reviewed": "No real evidence; synthetic fixture",
                "shop_name": "Synthetic Pharmacy" if role == "pharmacist" else "",
                "shop_license": "TEST-SHOP-1" if role == "pharmacist" else "",
                "shop_license_expires": "2027-09-30" if role == "pharmacist" else None,
            }
        providers.append(row)
    patients = []
    for sid, _, _ in users[3:]:
        patients.append({
            "source_id": sid, "user": identities[sid],
            "profile": {"date_of_birth": "1990-01-01", "gender": "other", "blood_group": "unknown", "allergy_status": "unknown"},
            "geography": {"station": "Synthetic station", "line": "Central"},
            "records": [{"source_id": sid + "-VISIT1", "doctor_source_id": "DOC001",
                         "recorded_at": visit, "complaint": "Synthetic checkup", "diagnosis": "Synthetic example",
                         "notes": "Synthetic data only", "vitals": {"systolic": 120, "diastolic": 80, "glucose_mg_dl": 95}}],
            "entries": [{"kind": "condition", "name": "Synthetic condition", "notes": "Synthetic",
                         "source": "clinician_recorded", "author_source_id": "DOC001", "recorded_at": visit}],
            "labs": [{"doctor_source_id": "DOC001", "name": "Synthetic lab", "value": "95.00000", "unit": "mg/dL", "measured_at": visit}],
            "prescriptions": [{"source_id": sid + "-RX1", "doctor_source_id": "DOC001", "record_source_id": sid + "-VISIT1",
                               "issued_at": visit, "valid_until": "2026-09-22T10:00:00+00:00", "notes": "Synthetic example, not clinical advice",
                               "items": [{"medicine": "Synthetic medicine", "dosage": "Synthetic example", "quantity": "6.000", "unit": "tablet", "instructions": "Not for actual use"}]}],
            "adherence": [{"date": "2026-09-15", "scheduled_doses": 2, "taken_doses": 1}],
        })
    data = {"metadata": {"schema_version": 1, "dataset_id": "mumbai_stations_v1", "synthetic": True,
                         "seed": 20260929, "as_of": "2026-09-29"},
            "stations": [], "providers": providers, "patients": patients}
    credentials = {"dataset_id": "mumbai_stations_v1", "synthetic": True, "accounts": [
        {"source_id": sid, "email": identities[sid]["email"], "name": name, "role": role,
         "password": f"Isolated-fixture-passphrase!{index}7xQ"}
        for index, (sid, role, name) in enumerate(users)
    ]}
    return data, credentials


class SyntheticImportTests(TestCase):
    def setUp(self):
        local = settings.BASE_DIR.parent / ".local"
        local.mkdir(exist_ok=True)
        self.directory = TemporaryDirectory(prefix="synthetic-import-test-", dir=local)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.dataset = self.root / "dataset.json"
        self.credentials = self.root / "credentials.json"
        self.mapping = self.root / "mapping.json"
        self.data, self.secrets = fixture()
        self.write_inputs()

    def write_inputs(self):
        self.dataset.write_text(json.dumps(self.data), encoding="utf-8")
        self.credentials.write_text(json.dumps(self.secrets), encoding="utf-8")

    def command(self, apply=False):
        output = StringIO()
        call_command("import_synthetic_dataset", dataset=str(self.dataset), credentials=str(self.credentials),
                     mapping=str(self.mapping), apply=apply, stdout=output)
        return output.getvalue()

    def apply_in_test_database(self):
        # Only bypass target selection; all import/transaction/hash logic runs normally
        # against Django's isolated test database, never against a supplied URL.
        with patch.object(Command, "require_target"):
            return self.command(apply=True)

    def test_default_dry_run_performs_no_database_queries_or_writes(self):
        with self.assertNumQueries(0):
            output = self.command()
        self.assertIn("Dry run passed: 2 synthetic patients", output)
        self.assertFalse(self.mapping.exists())
        self.assertEqual(User.objects.count(), 0)
        for account in self.secrets["accounts"]:
            self.assertNotIn(account["password"], output)

    def test_medylink_domain_uses_existing_stable_import_identity(self):
        for row in [*self.data["providers"], *self.data["patients"]]:
            row["user"]["email"] = row["user"]["email"].replace("@synthetic.arogyatrack.test", "@synthetic.medylink.test")
        for account in self.secrets["accounts"]:
            account["email"] = account["email"].replace("@synthetic.arogyatrack.test", "@synthetic.medylink.test")
        self.write_inputs()
        self.apply_in_test_database()
        for account in self.secrets["accounts"]:
            user = User.objects.get(email=account["email"])
            self.assertEqual(user.id, uuid5(NAMESPACE_URL, f"arogyatrack:mumbai_stations_v1:users:{account['source_id']}"))
        before = set(User.objects.values_list("id", flat=True))
        with self.assertRaisesMessage(CommandError, "existing mapping is never overwritten"):
            self.apply_in_test_database()
        self.assertEqual(set(User.objects.values_list("id", flat=True)), before)

    @override_settings(SYNTHETIC_IMPORT_ALLOWED=False)
    def test_normal_settings_are_refused_before_database_access(self):
        with self.assertNumQueries(0), self.assertRaisesMessage(CommandError, "normal settings are refused"):
            self.command(apply=True)
        self.assertFalse(self.mapping.exists())

    @override_settings(SYNTHETIC_IMPORT_ALLOWED=True, DEBUG=True)
    def test_target_guard_rejects_nondedicated_database(self):
        with self.assertNumQueries(0), self.assertRaisesMessage(CommandError, "dedicated synthetic_"):
            Command().require_target()

    def test_nonempty_database_is_refused_without_touching_existing_account(self):
        user = User.objects.create_user("existing@example.test", "Existing-fixture-password!", name="Existing")
        original = user.password
        with self.assertRaisesMessage(CommandError, "not empty"):
            self.apply_in_test_database()
        user.refresh_from_db()
        self.assertEqual(user.password, original)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(self.mapping.exists())

    def test_hash_preparation_precedes_import_transaction_and_is_not_repeated(self):
        outer_depth = len(connection.atomic_blocks)
        original_prepare, original_import = Command.prepare_password_hashes, Command.import_rows
        states = []

        def prepare(command, passwords):
            states.append(("prepare", len(connection.atomic_blocks)))
            with self.assertNumQueries(0):
                return original_prepare(command, passwords)

        def import_rows(command, data, passwords, checksum, prepared_hashes=None):
            states.append(("import", len(connection.atomic_blocks)))
            self.assertEqual(set(prepared_hashes), set(passwords))
            with patch("clinic.management.commands.import_synthetic_dataset.make_password", side_effect=AssertionError("hashing inside import transaction")):
                return original_import(command, data, passwords, checksum, prepared_hashes=prepared_hashes)

        with patch.object(Command, "prepare_password_hashes", prepare), patch.object(Command, "import_rows", import_rows):
            self.apply_in_test_database()
        self.assertEqual(states, [("prepare", outer_depth), ("import", outer_depth + 1)])
        self.assertEqual(User.objects.count(), 5)

    def test_account_arriving_during_hash_preparation_is_rejected_by_final_guard(self):
        original_prepare = Command.prepare_password_hashes

        def prepare(command, passwords):
            result = original_prepare(command, passwords)
            User.objects.create_user("arrived-during-preparation@example.test", "Concurrent-test-password!947", name="Existing account")
            return result

        with patch.object(Command, "prepare_password_hashes", prepare):
            with self.assertRaisesMessage(CommandError, "not empty"):
                self.apply_in_test_database()
        self.assertEqual(User.objects.count(), 1)
        self.assertTrue(User.objects.filter(email="arrived-during-preparation@example.test").exists())
        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(SecurityEvent.objects.count(), 0)
        self.assertFalse(self.mapping.exists())

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"])
    def test_apply_preserves_hashes_relations_dates_and_provenance(self):
        output = self.apply_in_test_database()
        self.assertIn("Imported 2 synthetic patients", output)
        self.assertEqual(User.objects.count(), 5)
        self.assertEqual(Patient.objects.count(), 2)
        self.assertEqual(ProviderApplication.objects.count(), 2)
        self.assertEqual(MedicalRecord.objects.count(), 2)
        self.assertEqual(DoctorPatient.objects.count(), 2)
        self.assertEqual(ClinicalEntry.objects.count(), 2)
        self.assertEqual(LabResult.objects.count(), 2)
        self.assertEqual(MedicationAdherenceLog.objects.count(), 2)
        self.assertEqual(PrescriptionItem.objects.count(), 2)
        self.assertEqual(AuthSession.objects.count(), 0)
        for account in self.secrets["accounts"]:
            user = User.objects.get(email=account["email"])
            self.assertTrue(user.check_password(account["password"]))
            self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
            self.assertTrue(user.email_verified)
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
            prefix = ACCOUNT_ID_PREFIXES[user.role]
            self.assertRegex(user.account_id, rf"^{prefix}-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{{6}}$")
            self.assertEqual(user.id, uuid5(NAMESPACE_URL, f"arogyatrack:mumbai_stations_v1:users:{account['source_id']}"))
            self.assertEqual(user.created_at.year, 2025)
        self.assertEqual(len(set(User.objects.values_list("account_id", flat=True))), 5)
        self.assertEqual(len(set(User.objects.values_list("password", flat=True))), 5)
        expected = datetime(2026, 9, 15, 10, tzinfo=dt_timezone.utc)
        for rx in Prescription.objects.select_related("record", "application"):
            self.assertEqual(rx.record.patient_id, rx.patient_id)
            self.assertEqual(rx.record.doctor_id, rx.doctor_id)
            self.assertEqual(rx.application.provider_id, rx.doctor_id)
            self.assertEqual(rx.created_at, expected)
            self.assertEqual(rx.record.created_at, expected)
            self.assertEqual(rx.items.get().created_at, expected)
            self.assertEqual(str(rx.items.get().quantity), "6.000")
        self.assertEqual(SecurityEvent.objects.filter(event="synthetic_dataset_import").count(), 5)
        mapping_text = self.mapping.read_text(encoding="utf-8")
        mapping = json.loads(mapping_text)
        self.assertEqual(mapping["dataset_id"], "mumbai_stations_v1")
        self.assertEqual(len(mapping["entities"]["patients"]), 2)
        for account in self.secrets["accounts"]:
            self.assertNotIn(account["password"], mapping_text)
        account = self.secrets["accounts"][-1]
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/v1/auth/csrf/").data["csrfToken"]
        response = client.post("/api/v1/auth/login/", {"email": account["email"], "password": account["password"]},
                               format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies["access_token"]["httponly"])
        with self.assertRaisesMessage(CommandError, "existing mapping"):
            self.apply_in_test_database()

    def test_invalid_credentials_or_cross_patient_record_fail_offline(self):
        original = copy.deepcopy(self.data)
        self.data["patients"][1]["prescriptions"][0]["record_source_id"] = "PAT0001-VISIT1"
        self.write_inputs()
        with self.assertNumQueries(0), self.assertRaisesMessage(CommandError, "record must belong"):
            self.command()
        self.data = original
        self.secrets["accounts"][0]["password"] = "short"
        self.write_inputs()
        with self.assertNumQueries(0), self.assertRaisesMessage(CommandError, "password does not meet"):
            self.command()

    def test_existing_mapping_is_never_overwritten(self):
        self.mapping.write_text("keep this file", encoding="utf-8")
        with self.assertNumQueries(0), self.assertRaisesMessage(CommandError, "existing mapping"):
            self.apply_in_test_database()
        self.assertEqual(self.mapping.read_text(), "keep this file")

    def test_insert_failure_rolls_back_accounts_and_removes_new_mapping(self):
        with patch.object(Prescription.objects, "bulk_create", side_effect=RuntimeError("fixture failure")):
            with self.assertRaisesMessage(RuntimeError, "fixture failure"):
                self.apply_in_test_database()
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Patient.objects.count(), 0)
        self.assertFalse(self.mapping.exists())

    def test_account_id_collision_is_retried_before_batch_insertion(self):
        generated = ["D-AAAAAA", "PH-AAAAAA", "A-AAAAAA", "P-AAAAAA", "P-AAAAAA", "P-BBBBBB"]
        with patch("clinic.management.commands.import_synthetic_dataset.generate_account_id", side_effect=generated) as generate:
            self.apply_in_test_database()
        self.assertEqual(generate.call_count, 6)
        self.assertEqual(User.objects.count(), 5)
        self.assertEqual(set(User.objects.filter(role="patient").values_list("account_id", flat=True)), {"P-AAAAAA", "P-BBBBBB"})

    def test_exhausted_account_id_collisions_leave_no_partial_import(self):
        with patch("clinic.management.commands.import_synthetic_dataset.generate_account_id", return_value="D-AAAAAA"):
            with self.assertRaisesMessage(CommandError, "unique synthetic account ID"):
                self.apply_in_test_database()
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(SecurityEvent.objects.count(), 0)
        self.assertFalse(self.mapping.exists())

    def test_credentials_outside_ignored_directory_are_refused_offline(self):
        with self.assertNumQueries(0), self.assertRaisesMessage(CommandError, "ignored .local"):
            call_command("import_synthetic_dataset", dataset=str(self.dataset),
                         credentials=str(settings.BASE_DIR / "public-credentials.json"),
                         mapping=str(self.mapping), stdout=StringIO())

    def test_alternate_dataset_identity_is_supported_offline(self):
        self.data["metadata"]["dataset_id"] = "mumbai_validation_seed2"
        self.secrets["dataset_id"] = "mumbai_validation_seed2"
        self.write_inputs()
        with self.assertNumQueries(0):
            self.assertIn("Dry run passed", self.command())

    def test_mapping_write_failure_rolls_back_database(self):
        with patch("clinic.management.commands.import_synthetic_dataset.os.fsync", side_effect=OSError("fixture write failure")):
            with self.assertRaisesMessage(OSError, "fixture write failure"):
                self.apply_in_test_database()
        self.assertEqual(User.objects.count(), 0)
        self.assertFalse(self.mapping.exists())

    def test_synthetic_settings_never_fall_back_to_normal_url(self):
        # Import settings in a fresh process without django.setup or any connection.
        env = {**os.environ, "DJANGO_DEBUG": "true", "DATABASE_URL": "postgresql://unused:unused@invalid.test/normal_database",
               "PYTHONPATH": str(settings.BASE_DIR)}
        for url, succeeds in [
            ("", False),
            ("postgresql://unused:unused@invalid.test/normal_database", False),
            ("postgresql://unused:unused@invalid.test/synthetic_fixture?dbname=normal_database", False),
            ("postgresql://unused:unused@invalid.test/synthetic_fixture?sslmode=require&channel_binding=require", True),
        ]:
            with self.subTest(valid=succeeds, configured=bool(url)):
                env["SYNTHETIC_DATABASE_URL"] = url
                code = (
                    "import config.synthetic_settings as s; "
                    "assert s.DATABASES['default']['NAME'] == 'synthetic_fixture'; "
                    "assert s.SYNTHETIC_IMPORT_ALLOWED"
                )
                result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, timeout=30)
                self.assertEqual(result.returncode == 0, succeeds)
