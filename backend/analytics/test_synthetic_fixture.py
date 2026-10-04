"""Public fixture reproduction and guarded append; never uses a live database."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from accounts.models import SecurityEvent, User
from clinic.models import LabResult, MedicalRecord, Patient, ProviderApplication
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from .models import DatasetBatch, DiseaseObservation, PatientAreaObservation, StationArea
from .synthetic_fixture import (
    BASE_DIRECTORY, DEFAULT_DIRECTORY, ROOT, FixtureError,
    apply_fixture, build_fixture, load_fixture,
)


class PublicExpansionTests(SimpleTestCase):
    def test_published_fixture_counts_reproducibility_and_original_preservation(self):
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in BASE_DIRECTORY.iterdir() if path.is_file()}
        package = load_fixture()
        self.assertEqual(package["manifest"]["counts"], {
            "patients": 3000, "visits": 8987, "derived_labs": 25596,
            "derived_disease_observations": 10325, "stations": 34,
            "base_patients": 1000, "combined_patients": 4000,
        })
        self.assertEqual(len({row["id"] for row in package["patients"]}), 3000)
        self.assertEqual(len({visit["id"] for row in package["patients"] for visit in row["visits"]}), 8987)
        with TemporaryDirectory() as directory:
            build_fixture(directory)
            for name in ("patients.jsonl", "visits.jsonl", "manifest.json"):
                self.assertEqual((Path(directory) / name).read_bytes(), (DEFAULT_DIRECTORY / name).read_bytes())
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in BASE_DIRECTORY.iterdir() if path.is_file()}
        self.assertEqual(before, after)

    def test_builder_runs_without_django_site_packages_or_environment_settings(self):
        with TemporaryDirectory() as directory:
            env = {key: value for key, value in os.environ.items()
                   if not any(token in key for token in ("DATABASE", "DJANGO", "SECRET", "TOKEN", "PASSWORD"))}
            result = subprocess.run([sys.executable, "-S", str(ROOT / "scripts/build_synthetic_expansion.py"), "--output", directory],
                                    env=env, cwd=directory, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, "Offline fixture builder failed without site packages.")
            self.assertEqual(json.loads(result.stdout)["counts"]["patients"], 3000)
            self.assertTrue((Path(directory) / "visits.jsonl").exists())

    def test_manifest_tampering_truncated_rows_and_rehashed_changes_are_refused(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = build_fixture(root, count=6)
            original_manifest = (root / "manifest.json").read_bytes()
            patients = (root / "patients.jsonl").read_bytes()
            changed = dict(manifest, synthetic=False)
            (root / "manifest.json").write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(FixtureError):
                load_fixture(root)
            (root / "manifest.json").write_bytes(original_manifest)
            (root / "patients.jsonl").write_bytes(patients.split(b"\n", 1)[1])
            with self.assertRaises(FixtureError):
                load_fixture(root)
            tampered = patients.replace(b'"gender":"male"', b'"gender":"other"', 1)
            self.assertNotEqual(tampered, patients)
            (root / "patients.jsonl").write_bytes(tampered)
            manifest["files"]["patients.jsonl"] = {"sha256": hashlib.sha256(tampered).hexdigest(), "bytes": len(tampered)}
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesMessage(FixtureError, "Manifest"):
                load_fixture(root)


class ExpansionImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.directory = TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        build_fixture(cls.directory.name, count=6)
        cls.package = load_fixture(cls.directory.name)
        cls.batch = DatasetBatch.objects.create(
            key="mumbai_stations_v1", synthetic=True, generator_version="base", seed=20260929,
            as_of=date(2026, 9, 29), observation_start=date(2025, 9, 30),
            manifest_hash="b" * 64, dataset_hash=cls.package["manifest"]["base"]["sha256"],
            patient_count=1000, observation_count=2394)
        stations = [StationArea(batch=cls.batch, key=row["key"], name=row["name"], latitude=row["latitude"], longitude=row["longitude"])
                    for row in cls.package["stations"]]
        StationArea.objects.bulk_create(stations)
        users = [User(email=f"base-{number}@synthetic.test", account_id=f"P-{number:06}", name="Base fixture patient", password="!")
                 for number in range(1000)]
        User.objects.bulk_create(users)
        patients = [Patient(id=pk, user=user, date_of_birth=date(1990, 1, 1))
                    for (key, pk), user in zip(cls.package["base_patient_ids"].items(), users)]
        Patient.objects.bulk_create(patients)
        PatientAreaObservation.objects.bulk_create([
            PatientAreaObservation(batch=cls.batch, patient=patient, source_key=key, station=stations[0],
                                   latitude=19, longitude=73, coordinate_source="base", valid_at=cls.batch.as_of)
            for key, patient in zip(cls.package["base_patient_ids"], patients)])
        cls.doctor = User.objects.create_user("doctor@synthetic.test", name="Base fixture doctor", role="doctor")
        ProviderApplication.objects.create(provider=cls.doctor, version=1, status="approved", is_current=True,
                                           registration_number="TEST", registering_body="SYNTHETIC", practice_address="SYNTHETIC")
        cls.original = MedicalRecord.objects.create(patient=patients[0], doctor=cls.doctor, complaint="Preserve base record", vitals={"systolic": 120})

    def apply(self):
        with patch("clinic.management.commands.import_synthetic_dataset.Command.require_target"):
            return apply_fixture(self.package)

    def test_default_command_is_database_free_and_normal_apply_target_is_refused(self):
        with self.assertNumQueries(0):
            output = StringIO()
            call_command("import_synthetic_expansion", dataset_dir=self.directory.name, stdout=output)
        self.assertIn("Dry run passed", output.getvalue())
        with override_settings(SYNTHETIC_IMPORT_ALLOWED=False), self.assertNumQueries(0), self.assertRaises(CommandError):
            call_command("import_synthetic_expansion", dataset_dir=self.directory.name, apply=True, stdout=StringIO())

    def test_append_repeat_and_base_preservation(self):
        before = DatasetBatch.objects.values().get(pk=self.batch.pk)
        original = MedicalRecord.objects.values().get(pk=self.original.pk)
        base_users = list(User.objects.order_by("id").values())
        result = self.apply()
        self.assertEqual(result["created_patients"], 6)
        self.assertEqual(Patient.objects.count(), 1006)
        self.assertEqual(MedicalRecord.objects.count(), 1 + self.package["manifest"]["counts"]["visits"])
        self.assertEqual(LabResult.objects.count(), self.package["manifest"]["counts"]["derived_labs"])
        self.assertEqual(DiseaseObservation.objects.count(), self.package["manifest"]["counts"]["derived_disease_observations"])
        events = SecurityEvent.objects.count()
        self.assertEqual(self.apply()["created_patients"], 0)
        self.assertEqual(SecurityEvent.objects.count(), events)
        self.assertEqual(Patient.objects.count(), 1006)
        self.assertEqual(DatasetBatch.objects.values().get(pk=self.batch.pk), before)
        self.assertEqual(MedicalRecord.objects.values().get(pk=self.original.pk), original)
        self.assertEqual(list(User.objects.filter(pk__in=[row["id"] for row in base_users]).order_by("id").values()), base_users)
        self.assertTrue(all(not user.is_active and not user.has_usable_password()
                            for user in User.objects.filter(pk__in=[row["user_id"] for row in self.package["patients"]])))

    def test_patients_created_by_existing_generator_are_recognized_as_same_fixture(self):
        from .synthetic_generation import append_synthetic_patients

        with patch("clinic.management.commands.import_synthetic_dataset.Command.require_target"):
            original = append_synthetic_patients(count=6, seed=42)
        before = list(MedicalRecord.objects.order_by("id").values())
        self.assertEqual(original["created_patients"], 6)
        self.assertEqual(self.apply()["created_patients"], 0)
        self.assertEqual(list(MedicalRecord.objects.order_by("id").values()), before)
        self.assertEqual(Patient.objects.count(), 1006)

    def test_incomplete_or_wrong_base_is_refused(self):
        self.batch.dataset_hash = "x" * 64
        self.batch.save(update_fields=["dataset_hash"])
        with self.assertRaisesMessage(CommandError, "base clinical"):
            self.apply()
        self.batch.dataset_hash = self.package["manifest"]["base"]["sha256"]
        self.batch.save(update_fields=["dataset_hash"])
        self.batch.areas.first().delete()
        with self.assertRaisesMessage(CommandError, "complete, matching base"):
            self.apply()
        self.assertEqual(Patient.objects.count(), 1000)

    def test_new_identity_collision_preserves_existing_accounts(self):
        collision = User.objects.create_user("keep-collision@synthetic.test", name="Existing", id=self.package["patients"][0]["user_id"])
        with self.assertRaisesMessage(CommandError, "identities conflict"):
            self.apply()
        self.assertTrue(User.objects.filter(pk=collision.pk).exists())
        self.assertEqual(Patient.objects.count(), 1000)
        self.assertEqual(MedicalRecord.objects.count(), 1)

    def test_failure_after_user_inserts_rolls_back_whole_append(self):
        with patch.object(MedicalRecord.objects, "bulk_create", side_effect=RuntimeError("fixture insert failure")):
            with self.assertRaisesMessage(RuntimeError, "fixture insert failure"):
                self.apply()
        self.assertEqual(User.objects.count(), 1001)
        self.assertEqual(Patient.objects.count(), 1000)
        self.assertEqual(PatientAreaObservation.objects.count(), 1000)
        self.assertEqual(SecurityEvent.objects.count(), 0)

    def test_incomplete_existing_expansion_and_enabled_accounts_are_refused(self):
        self.apply()
        row = self.package["patients"][0]
        User.objects.filter(pk=row["user_id"]).update(is_active=True)
        with self.assertRaisesMessage(CommandError, "incomplete or has conflicting"):
            self.apply()
        User.objects.filter(pk=row["user_id"]).update(is_active=False)
        DiseaseObservation.objects.filter(medical_record_id=row["visits"][0]["id"]).delete()
        with self.assertRaisesMessage(CommandError, "incomplete or has conflicting"):
            self.apply()
        self.assertEqual(Patient.objects.count(), 1006)
