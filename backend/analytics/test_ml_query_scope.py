"""Avoid transferring unused lab values without changing cohort counts/features."""

from datetime import date, datetime, timezone
from unittest.mock import patch

from accounts.models import User
from clinic.models import LabResult, MedicalRecord, Patient
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from .ml_dataset import bounded, build_dataset
from .models import DatasetBatch, PatientAreaObservation, StationArea


@override_settings(SYNTHETIC_IMPORT_ALLOWED=True)
class MLLabQueryScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.batch = DatasetBatch.objects.create(key="lab_scope", synthetic=True, generator_version="test", seed=1, as_of=date(2026, 1, 31), observation_start=date(2025, 12, 1), manifest_hash="a" * 64, dataset_hash="b" * 64, patient_count=10, observation_count=0)
        cls.station = StationArea.objects.create(batch=cls.batch, key="KURLA", name="Kurla", lines=["Central"], latitude=19.06, longitude=72.88)
        cls.doctor = User.objects.create_user(email="lab-scope-doctor@test.invalid", name="Synthetic doctor", role="doctor")
        cls.patients = []
        for index in range(10):
            user = User.objects.create_user(email=f"lab-scope-patient{index}@test.invalid", name="Synthetic patient")
            patient = Patient.objects.create(user=user, date_of_birth=date(1980, 1, 1))
            cls.patients.append(patient)
            PatientAreaObservation.objects.create(batch=cls.batch, patient=patient, source_key=f"LAB-{index}", station=cls.station, latitude=19.06, longitude=72.88, coordinate_source="synthetic", valid_at=date(2025, 12, 1))
            record = MedicalRecord.objects.create(patient=patient, doctor=cls.doctor, complaint="Synthetic review", diagnosis="Asthma" if index < 6 else "Dengue", vitals={"blood_pressure": "120/80"})
            MedicalRecord.objects.filter(pk=record.pk).update(created_at=datetime(2026, 1, 15, 10, tzinfo=timezone.utc))
            for name, value, unit, measured in (
                ("FASTING GLUCOSE", 110 + index, " mg/dL ", datetime(2025, 12, 29, 10, tzinfo=timezone.utc)),
                ("Hemoglobin", 13, "g/dL", datetime(2026, 1, 10, 10, tzinfo=timezone.utc)),
                ("Platelet count", 250000, "/uL", datetime(2026, 1, 12, 10, tzinfo=timezone.utc)),
            ):
                lab = LabResult.objects.create(patient=patient, recorded_by=cls.doctor, name=name, value=value, unit=unit, measured_at=measured)
                LabResult.objects.filter(pk=lab.pk).update(created_at=measured)
        cls.filters = {"dataset_id": cls.batch.key, "date_from": None, "date_to": None, "disease_code": "", "line": "", "station_id": ""}

    def test_all_labs_are_counted_but_only_glucose_values_are_fetched(self):
        fetched_labs = []

        def read(query):
            rows = bounded(query)
            if query.model is LabResult:
                fetched_labs.extend(rows)
            return rows

        with patch("analytics.ml_dataset.bounded", side_effect=read):
            result = build_dataset(self.batch, self.filters)
        self.assertEqual(result["source"]["labs"], 30)
        self.assertEqual(len(fetched_labs), 10)
        self.assertEqual({row["name"] for row in fetched_labs}, {"FASTING GLUCOSE"})
        self.assertEqual(sorted(row["glucose"] for row in result["history"]), list(range(110, 120)))

    def test_date_and_disease_scoped_counts_include_non_glucose_labs(self):
        result = build_dataset(self.batch, {**self.filters, "disease_codes": "ASTHMA", "date_from": "2026-01-01", "date_to": "2026-01-31"})
        self.assertEqual(result["source"]["patients"], 6)
        self.assertEqual(result["source"]["labs"], 12)  # Hb + platelets for six people.
        self.assertEqual(sorted(row["glucose"] for row in result["cohort"]), list(range(110, 116)))
        # Glucose from December remains available as a chronological fallback,
        # although its lab row is outside the displayed January source count.
        day_only = build_dataset(self.batch, {**self.filters, "date_from": "2026-01-15", "date_to": "2026-01-15"})
        self.assertEqual(day_only["source"]["patients"], 10)
        self.assertEqual(day_only["source"]["labs"], 0)

    def test_historical_glucose_still_ignores_later_recording_and_wrong_units(self):
        for index, unit, created in (
            (0, "mg/dL", datetime(2026, 1, 20, 10, tzinfo=timezone.utc)),
            (1, "mmol/L", datetime(2026, 1, 14, 10, tzinfo=timezone.utc)),
        ):
            lab = LabResult.objects.create(patient=self.patients[index], recorded_by=self.doctor, name="Glucose", value=333, unit=unit, measured_at=datetime(2026, 1, 14, 10, tzinfo=timezone.utc))
            LabResult.objects.filter(pk=lab.pk).update(created_at=created)
        result = build_dataset(self.batch, self.filters)
        self.assertEqual(result["source"]["labs"], 32)
        self.assertNotIn(333, [row["glucose"] for row in result["history"]])
        # The current view can use the later-recorded mg/dL value; the original
        # historical snapshot above cannot. A mismatched unit is never used.
        self.assertEqual(sum(row["glucose"] == 333 for row in result["cohort"]), 1)

    def test_total_lab_guard_includes_values_not_loaded_for_features(self):
        # Ten consultations and ten glucose rows fit; thirty total lab rows do
        # not. Counting only glucose would accidentally bypass this safety bound.
        with patch("analytics.ml_dataset.MAX_ROWS", 12), self.assertRaises(ValidationError):
            build_dataset(self.batch, self.filters)
