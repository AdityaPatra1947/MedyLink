"""Appended synthetic visits extend coverage and invalidate cached aggregates."""

from datetime import date, datetime, timezone

from accounts.models import User
from clinic.models import ClinicalEntry, Patient
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    DatasetBatch,
    DiseaseCode,
    DiseaseObservation,
    PatientAreaObservation,
    StationArea,
)
from .services import execute_run, live_dataset_metadata, resolve_filters


class LiveDatasetMetadataTests(TestCase):
    def setUp(self):
        self.batch = DatasetBatch.objects.create(key="live_metadata", synthetic=True, generator_version="original", seed=1, as_of=date(2026, 9, 29), observation_start=date(2026, 9, 1), manifest_hash="a" * 64, dataset_hash="b" * 64, patient_count=1000, observation_count=1000)
        self.station = StationArea.objects.create(batch=self.batch, key="KURLA", name="Kurla", latitude=19.06, longitude=72.88)
        self.disease = DiseaseCode.objects.create(code="DENGUE", label="Dengue")
        self.admin = User.objects.create_user(email="metadata-admin@test.invalid", name="Synthetic admin", role="admin", email_verified_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
        self.sequence = 0

    def observation(self, when):
        self.sequence += 1
        user = User.objects.create_user(email=f"metadata-patient{self.sequence}@test.invalid", name="Synthetic patient", role="patient")
        patient = Patient.objects.create(user=user)
        area = PatientAreaObservation.objects.create(batch=self.batch, patient=patient, source_key=f"META-{self.sequence}", station=self.station, latitude=19.06, longitude=72.88, coordinate_source="synthetic", valid_at=when.date())
        entry = ClinicalEntry.objects.create(patient=patient, author=user, kind="condition", name="Dengue", source="synthetic")
        return DiseaseObservation.objects.create(batch=self.batch, patient=patient, area=area, disease=self.disease, observed_at=when, episode_key=f"META-{self.sequence}", import_key=f"META-{self.sequence}", age_band="30s", clinical_entry=entry)

    def test_live_window_and_count_do_not_overwrite_import_metadata(self):
        original = DatasetBatch.objects.values().get(pk=self.batch.pk)
        self.observation(datetime(2024, 10, 31, 10, tzinfo=timezone.utc))
        self.observation(datetime(2026, 9, 30, 10, tzinfo=timezone.utc))
        metadata = live_dataset_metadata(self.batch)
        self.assertEqual(metadata["patient_count"], 2)
        self.assertEqual(metadata["observation_count"], 2)
        self.assertEqual(metadata["observation_start"], date(2024, 10, 31))
        self.assertEqual(metadata["as_of"], date(2026, 9, 30))
        self.assertEqual(DatasetBatch.objects.values().get(pk=self.batch.pk), original)

    def test_empty_or_sparse_data_keeps_original_window_available(self):
        for _ in range(2):
            metadata = live_dataset_metadata(self.batch)
            self.assertEqual(metadata["observation_start"], self.batch.observation_start)
            self.assertEqual(metadata["as_of"], self.batch.as_of)
            self.observation(datetime(2026, 9, 15, 10, tzinfo=timezone.utc))

    def test_catalog_uses_live_coverage_and_suppresses_small_count(self):
        self.observation(datetime(2024, 10, 31, 10, tzinfo=timezone.utc))
        self.observation(datetime(2026, 9, 30, 10, tzinfo=timezone.utc))
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get("/api/v1/admin/analytics/catalog/", {"dataset_id": self.batch.key})
        self.assertEqual(response.status_code, 200)
        row = response.data["datasets"][0]
        self.assertIsNone(row["patient_count"])
        self.assertEqual(row["observation_start"], "2024-10-31")
        self.assertEqual(row["as_of"], "2026-09-30")
        self.assertEqual(response.data["defaults"]["date_to"], "2026-09-30")

    def test_filter_accepts_appended_history(self):
        self.observation(datetime(2024, 10, 31, 10, tzinfo=timezone.utc))
        batch, filters = resolve_filters({"dataset_id": self.batch.key, "date_from": date(2024, 10, 31), "date_to": date(2024, 11, 30), "disease_code": "DENGUE"})
        self.assertEqual(batch.pk, self.batch.pk)
        self.assertEqual(filters["date_from"], "2024-10-31")

    def test_append_invalidates_saved_run_without_changing_manifest(self):
        for _ in range(6):
            self.observation(datetime(2026, 9, 15, 10, tzinfo=timezone.utc))
        filters = {"dataset_id": self.batch.key, "date_from": "2026-09-01", "date_to": "2026-09-29", "disease_code": "DENGUE", "station_id": "", "line": ""}
        first, reused = execute_run(self.batch, self.admin, "cluster", filters, {"radius_km": .5, "min_samples": 5})
        self.assertFalse(reused)
        same, reused = execute_run(self.batch, self.admin, "cluster", filters, {"radius_km": .5, "min_samples": 5})
        self.assertTrue(reused)
        self.assertEqual(same.pk, first.pk)
        self.observation(datetime(2026, 9, 16, 10, tzinfo=timezone.utc))
        changed, reused = execute_run(self.batch, self.admin, "cluster", filters, {"radius_km": .5, "min_samples": 5})
        self.assertFalse(reused)
        self.assertNotEqual(changed.pk, first.pk)
        self.assertNotEqual(changed.cache_key, first.cache_key)
