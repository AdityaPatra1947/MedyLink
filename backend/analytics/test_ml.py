"""Isolation, chronology, filter and worker regressions for the new ML module."""

import json
from datetime import date, datetime, timedelta, timezone as dt_timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch

from accounts.models import User
from clinic.models import ClinicalEntry, LabResult, MedicalRecord, MedicalReport, MedicationAdherenceLog, Patient
from clinic.report_formats import MONTHLY_FORMATS
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .ml_dataset import build_dataset, recognized_diseases
from .ml_serializers import MLFilters
from .ml_services import artifact_dir, current_hotspots, enqueue_training, execute_training, public_json, run_payload
from .models import DatasetBatch, MLRun, PatientAreaObservation, StationArea

PREFIX = "/api/v1/admin/analytics/ml/"


def stamp(month, day=15):
    return datetime(2025, month, day, 10, tzinfo=dt_timezone.utc)


@override_settings(SYNTHETIC_IMPORT_ALLOWED=True)
class MLTests(TestCase):
    def setUp(self):
        self.admin = self.user("admin")
        self.doctor = self.user("doctor")
        self.patient = Patient.objects.create(user=self.user("patient"), date_of_birth=date(1980, 1, 1), gender="female")
        self.batch = DatasetBatch.objects.create(key="ml_test", synthetic=True, generator_version="test", seed=1, as_of=date(2025, 9, 1), observation_start=date(2025, 7, 1), manifest_hash="a" * 64, dataset_hash="b" * 64, patient_count=1, observation_count=0)
        self.station = StationArea.objects.create(batch=self.batch, key="KURLA", name="Kurla", lines=["Central", "Harbour"], latitude=19.065, longitude=72.88)
        self.area = PatientAreaObservation.objects.create(batch=self.batch, patient=self.patient, source_key="PRIVATE-PAT", station=self.station, latitude=19.06613, longitude=72.88137, coordinate_source="simulated_station_catchment_point", valid_at=self.batch.as_of)
        self.filters = {"dataset_id": self.batch.key, "date_from": None, "date_to": None, "disease_code": "", "line": "", "station_id": ""}
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def user(self, role, suffix=""):
        return User.objects.create_user(email=f"PRIVATE-{role}{suffix}@test.invalid", password="Private-test-password!123", name=f"PRIVATE {role} {suffix}", role=role, email_verified_at=timezone.now())

    def record(self, month, bp="130/80", diagnosis="Hypertension", patient=None, correction_of=None, day=15):
        row = MedicalRecord.objects.create(patient=patient or self.patient, doctor=self.doctor, complaint="PRIVATE symptom text", diagnosis=diagnosis, notes="PRIVATE encounter notes", vitals={"blood_pressure": bp}, correction_of=correction_of)
        MedicalRecord.objects.filter(pk=row.pk).update(created_at=stamp(month, day))
        row.refresh_from_db()
        return row

    def test_all_history_includes_dates_before_imported_analytics_window(self):
        self.record(1)
        self.record(8)
        data = build_dataset(self.batch, self.filters)
        self.assertEqual(len(data["history"]), 2)
        self.assertEqual(data["source"]["history_start"], "2025-01-15")
        self.assertEqual(data["source"]["history_end"], "2025-08-15")
        narrower = build_dataset(self.batch, {**self.filters, "date_from": "2025-07-01", "date_to": "2025-08-31"})
        self.assertEqual(len(narrower["cohort"]), 1)
        self.assertEqual(narrower["history"][0]["observed_at"][:10], "2025-08-15")
        self.assertNotEqual(data["source"]["snapshot_sha256"], narrower["source"]["snapshot_sha256"])

    def test_live_records_are_read_without_modifying_original_analytics_snapshot(self):
        self.record(1)
        first = build_dataset(self.batch, self.filters)
        self.record(2)
        second = build_dataset(self.batch, self.filters)
        self.assertEqual((len(first["history"]), len(second["history"])), (1, 2))
        self.assertEqual(self.batch.observations.count(), 0)

    def test_corrections_do_not_backfill_historical_features_or_duplicate_visits(self):
        original = self.record(1, "120/75", "Asthma")
        self.record(3, "175/105", "Hypertension", correction_of=original)
        current = build_dataset(self.batch, self.filters)
        self.assertEqual(len(current["history"]), 1)
        self.assertEqual(current["history"][0]["systolic"], 120)
        self.assertEqual(current["history"][0]["disease_codes"], ["ASTHMA"])
        self.assertEqual(current["cohort"][0]["systolic"], 175)
        early = build_dataset(self.batch, {**self.filters, "date_to": "2025-02-28"})
        self.assertEqual(early["cohort"][0]["systolic"], 120)

    def test_future_lab_condition_and_dose_log_are_not_historical_features(self):
        self.record(1)
        lab = LabResult.objects.create(patient=self.patient, recorded_by=self.doctor, name="Fasting glucose", unit="mg/dL", value=190, measured_at=stamp(1) - timedelta(days=2))
        LabResult.objects.filter(pk=lab.pk).update(created_at=stamp(2))
        condition = ClinicalEntry.objects.create(patient=self.patient, author=self.doctor, kind="condition", name="Type 2 diabetes", source="clinician_recorded")
        ClinicalEntry.objects.filter(pk=condition.pk).update(created_at=stamp(2))
        log = MedicationAdherenceLog.objects.create(patient=self.patient, date=stamp(1).date(), scheduled_doses=10, taken_doses=2)
        MedicationAdherenceLog.objects.filter(pk=log.pk).update(created_at=stamp(2))
        data = build_dataset(self.batch, self.filters)
        historical = data["history"][0]
        self.assertIsNone(historical["glucose"])
        self.assertIsNone(historical["adherence"])
        self.assertEqual(historical["condition_count"], 0)
        self.assertNotIn("TYPE2_DIABETES", historical["disease_codes"])
        early = build_dataset(self.batch, {**self.filters, "date_to": "2025-01-31"})
        self.assertIsNone(early["cohort"][0]["glucose"])

    def test_historical_adherence_uses_immutable_diary_not_later_editable_log(self):
        original = self.record(1)
        report = MedicalReport.objects.create(patient=self.patient, uploaded_by=self.doctor, record=original, name="private.pdf", storage_name="immutable.pdf", content_type="application/pdf", size_bytes=10, extraction={"status": "extracted", "format": "arogyatrack-monthly-v1", "measured_at": stamp(1).isoformat(), "blood_pressure": {"systolic": 130, "diastolic": 80, "unit": "mmHg"}, "blood_sugar": {}, "adherence": {"daily": [{"date": stamp(1).date().isoformat(), "scheduled_doses": 4, "taken_doses": 3}]}})
        MedicalReport.objects.filter(pk=report.pk).update(created_at=stamp(1))
        edited = MedicationAdherenceLog.objects.create(patient=self.patient, date=stamp(1).date(), scheduled_doses=4, taken_doses=0)
        MedicationAdherenceLog.objects.filter(pk=edited.pk).update(created_at=stamp(1))
        data = build_dataset(self.batch, self.filters)
        self.assertEqual(data["history"][0]["adherence"], 75)
        self.assertEqual(data["cohort"][0]["adherence"], 0)

    def test_unversioned_diary_never_enters_historical_training(self):
        self.record(1)
        log = MedicationAdherenceLog.objects.create(patient=self.patient, date=stamp(1).date(), scheduled_doses=4, taken_doses=3)
        MedicationAdherenceLog.objects.filter(pk=log.pk).update(created_at=stamp(1) - timedelta(hours=1))
        data = build_dataset(self.batch, self.filters)
        self.assertIsNone(data["history"][0]["adherence"])
        self.assertEqual(data["cohort"][0]["adherence"], 75)

    def test_disease_filter_marks_index_but_keeps_intervening_visit_target(self):
        self.record(1, "120/75", "Asthma")
        self.record(2, "160/95", "Influenza")
        self.record(3, "125/76", "Asthma")
        data = build_dataset(self.batch, {**self.filters, "disease_code": "ASTHMA"})
        self.assertEqual(len(data["history"]), 3)
        self.assertEqual([row["eligible_index"] for row in data["history"]], [True, False, True])
        self.assertEqual(len(data["cohort"]), 2)
        from .ml_services import pipeline
        _, y, _, _ = pipeline().prepare_pairs(data["history"])
        self.assertEqual(y.tolist(), [1])

    def test_late_uploaded_report_is_excluded_historically_and_deduplicated_currently(self):
        original = self.record(1, "120/75")
        report = MedicalReport.objects.create(patient=self.patient, uploaded_by=self.doctor, record=original, name="private.pdf", storage_name="private.pdf", content_type="application/pdf", size_bytes=10, extraction={"status": "extracted", "format": "arogyatrack-monthly-v1", "measured_at": stamp(1).isoformat(), "blood_pressure": {"systolic": 150, "diastolic": 95, "unit": "mmHg"}, "blood_sugar": {"value": 100, "unit": "mg/dL", "context": "fasting"}})
        MedicalReport.objects.filter(pk=report.pk).update(created_at=stamp(2))
        for report_format in MONTHLY_FORMATS:
            with self.subTest(report_format=report_format):
                report.extraction["format"] = report_format
                report.save(update_fields=["extraction"])
                data = build_dataset(self.batch, self.filters)
                self.assertEqual(len(data["cohort"]), 1)
                self.assertEqual(data["cohort"][0]["systolic"], 150)
                self.assertEqual(data["history"][0]["systolic"], 120)
                early = build_dataset(self.batch, {**self.filters, "date_to": "2025-01-31"})
                self.assertEqual(early["source"]["reports"], 0)

    def test_newer_correction_wins_over_old_attached_report_for_current_cohort(self):
        original = self.record(1, "120/75")
        report = MedicalReport.objects.create(patient=self.patient, uploaded_by=self.doctor, record=original, name="private.pdf", storage_name="older-report.pdf", content_type="application/pdf", size_bytes=10, extraction={"status": "extracted", "format": "arogyatrack-monthly-v1", "measured_at": stamp(1).isoformat(), "blood_pressure": {"systolic": 121, "diastolic": 76, "unit": "mmHg"}, "blood_sugar": {}})
        MedicalReport.objects.filter(pk=report.pk).update(created_at=stamp(1))
        self.record(2, "150/95", correction_of=original)
        data = build_dataset(self.batch, self.filters)
        self.assertEqual(len(data["cohort"]), 1)
        self.assertEqual(data["cohort"][0]["systolic"], 150)
        self.assertEqual(data["history"][0]["systolic"], 121)

    def test_uncoded_diagnosis_is_unknown_rather_than_no_disease(self):
        self.record(1, diagnosis="A condition outside the curated dictionary")
        data = build_dataset(self.batch, self.filters)
        self.assertEqual(data["cohort"][0]["disease_codes"], ["UNKNOWN"])

    def test_source_counts_follow_selected_dates(self):
        self.record(1)
        for index in range(5):
            lab = LabResult.objects.create(patient=self.patient, recorded_by=self.doctor, name="Glucose", unit="mg/dL", value=100, measured_at=stamp(1, index + 1))
            LabResult.objects.filter(pk=lab.pk).update(created_at=stamp(1, index + 1))
        for index in range(5):
            lab = LabResult.objects.create(patient=self.patient, recorded_by=self.doctor, name="Glucose", unit="mg/dL", value=100, measured_at=stamp(2, index + 1))
            LabResult.objects.filter(pk=lab.pk).update(created_at=stamp(2, index + 1))
        january = build_dataset(self.batch, {**self.filters, "date_to": "2025-01-31"})
        self.assertEqual(january["source"]["labs"], 5)
        all_history = build_dataset(self.batch, self.filters)
        self.assertEqual(all_history["source"]["labs"], 10)

    def test_missing_geography_not_imputed_and_unmapped_patient_is_numeric_eligible(self):
        self.record(1)
        self.area.latitude = self.area.longitude = None
        self.area.save(update_fields=["latitude", "longitude"])
        other = Patient.objects.create(user=self.user("patient", "new"), date_of_birth=date(1980, 1, 1))
        self.record(1, patient=other)
        data = build_dataset(self.batch, self.filters)
        self.assertEqual(len(data["history"]), 2)
        self.assertTrue(all(row["latitude"] is None and row["longitude"] is None for row in data["cohort"]))
        self.assertIn(current_hotspots(data["cohort"])["counts"]["with_coordinates"], (0, None))
        self.assertEqual(current_hotspots(data["cohort"])["counts"]["cluster_count"], 0)
        selected = build_dataset(self.batch, {**self.filters, "station_id": "KURLA"})
        self.assertEqual(len(selected["history"]), 1)
        with override_settings(SYNTHETIC_IMPORT_ALLOWED=False):
            scoped = build_dataset(self.batch, self.filters)
        self.assertEqual(len(scoped["history"]), 1)

    def test_known_disease_mapper_ignores_negative_and_family_history_mentions(self):
        self.assertEqual(recognized_diseases("No hypertension. Family history of type 2 diabetes. Asthma."), {"ASTHMA"})

    def test_filter_validation_rejects_unknown_reversed_and_future_dates(self):
        for extra in [{"arbitrary": "x"}, {"date_from": "2025-03-01", "date_to": "2025-02-01"}, {"date_to": (timezone.localdate() + timedelta(days=1)).isoformat()}]:
            self.assertFalse(MLFilters(data={**self.filters, **extra}).is_valid())

    def test_every_ml_route_requires_verified_admin(self):
        paths = ["catalog/", "insights/", "runs/", "runs/00000000-0000-0000-0000-000000000001/"]
        for role in (None, "patient", "doctor", "pharmacist"):
            self.client.force_authenticate(None if role is None else self.user(role, "forbidden"))
            for path in paths:
                response = self.client.get(PREFIX + path, {"dataset_id": self.batch.key})
                self.assertEqual(response.status_code, 401 if role is None else 403)
            self.assertEqual(self.client.post(PREFIX + "runs/", self.filters, format="json").status_code, 401 if role is None else 403)
        self.admin.email_verified_at = None
        self.admin.save(update_fields=["email_verified_at"])
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(PREFIX + "catalog/").status_code, 403)

    def test_training_requires_csrf_cookie_and_token(self):
        browser = APIClient(enforce_csrf_checks=True)
        csrf = browser.get("/api/v1/auth/csrf/").data["csrfToken"]
        browser.credentials(HTTP_X_CSRFTOKEN=csrf)
        logged_in = browser.post("/api/v1/auth/login/", {"email": self.admin.email, "password": "Private-test-password!123"}, format="json")
        self.assertEqual(logged_in.status_code, 200)
        browser.credentials()
        self.assertEqual(browser.post(PREFIX + "runs/", self.filters, format="json").status_code, 403)
        self.assertEqual(MLRun.objects.count(), 0)

    def test_api_returns_aggregates_not_patient_details(self):
        self.record(1)
        response = self.client.get(PREFIX + "insights/", {"dataset_id": self.batch.key})
        self.assertEqual(response.status_code, 200, response.data)
        body = json.dumps(response.data)
        for forbidden in ("PRIVATE", str(self.patient.pk), str(self.patient.user_id), self.patient.user.account_id, '"patient_key":', '"patient_id":', '"complaint":', '"diagnosis":', '"storage_name":', str(self.area.latitude)):
            self.assertNotIn(forbidden, body)
        self.assertIsNone(response.data["summary"]["patients"])
        self.assertTrue(response.data["synthetic"])

    def test_single_flight_and_failed_job_keep_previous_model(self):
        previous = MLRun.objects.create(batch=self.batch, actor=self.admin, status="completed", is_active_model=True, report={"selection": {"prediction_enabled": False}})
        run, reused = enqueue_training(self.batch, self.admin, self.filters, asynchronous=False)
        same, second_reused = enqueue_training(self.batch, self.admin, self.filters, asynchronous=False)
        self.assertFalse(reused)
        self.assertTrue(second_reused)
        self.assertEqual(same.pk, run.pk)
        with patch("analytics.ml_services.close_old_connections"), patch("analytics.ml_services.pipeline", side_effect=RuntimeError("PRIVATE failure detail")):
            failed = execute_training(run.id)
        previous.refresh_from_db()
        self.assertTrue(previous.is_active_model)
        self.assertEqual(failed.status, "failed")
        self.assertNotIn("PRIVATE", failed.error)
        self.assertIn("Predictions are unavailable", run_payload(previous)["message"])

    def test_successful_job_publishes_atomically_only_after_bundle_exists(self):
        previous = MLRun.objects.create(batch=self.batch, actor=self.admin, status="completed", is_active_model=True)
        run, _ = enqueue_training(self.batch, self.admin, self.filters, asynchronous=False)
        with TemporaryDirectory() as temp, override_settings(ML_ARTIFACT_ROOT=temp):
            def train(rows, directory):
                directory.mkdir(parents=True)
                (directory / "model_bundle.joblib").write_bytes(b"test-only-placeholder")
                return {"status": "completed", "selection": {"prediction_enabled": True}}
            with patch("analytics.ml_services.close_old_connections"), patch("analytics.ml_services.pipeline") as mocked:
                mocked.return_value.train_and_evaluate.side_effect = train
                result = execute_training(run.id)
        previous.refresh_from_db()
        self.assertFalse(previous.is_active_model)
        self.assertTrue(result.is_active_model)
        self.assertEqual(result.status, "completed")

    def test_insufficient_job_does_not_replace_successful_model(self):
        previous = MLRun.objects.create(batch=self.batch, actor=self.admin, status="completed", is_active_model=True)
        run, _ = enqueue_training(self.batch, self.admin, self.filters, asynchronous=False)
        with patch("analytics.ml_services.close_old_connections"), patch("analytics.ml_services.pipeline") as mocked:
            mocked.return_value.train_and_evaluate.return_value = {"status": "insufficient_data", "reason": "Not enough observations."}
            result = execute_training(run.id)
        previous.refresh_from_db()
        self.assertTrue(previous.is_active_model)
        self.assertFalse(result.is_active_model)
        self.assertEqual(result.status, "insufficient_data")

    def test_insights_filters_drive_all_three_analysis_inputs(self):
        self.record(1)
        self.record(2)
        MLRun.objects.create(batch=self.batch, actor=self.admin, status="completed", is_active_model=True)
        with patch("analytics.ml_services.pipeline") as mocked, patch("analytics.ml_services.current_hotspots") as hotspots:
            mocked.return_value.predict_summary.return_value = {"status": "completed", "counts": None}
            mocked.return_value.cluster_patient_groups.return_value = {"status": "insufficient_data", "groups": []}
            hotspots.return_value = {"clusters": [], "counts": {}, "notes": []}
            response = self.client.get(PREFIX + "insights/", {"dataset_id": self.batch.key, "date_from": "2025-02-01", "date_to": "2025-02-28"})
        self.assertEqual(response.status_code, 200, response.data)
        for call in (mocked.return_value.predict_summary.call_args, mocked.return_value.cluster_patient_groups.call_args, hotspots.call_args):
            self.assertEqual(len(call.args[0]), 1)
            self.assertEqual(call.args[0][0]["observed_at"][:7], "2025-02")

    def test_direct_and_pooled_connections_share_only_the_same_database_artifacts(self):
        run = MLRun(batch=self.batch, actor=self.admin)
        db = {**settings.DATABASES["default"], "HOST": "ep-example.c-7.us-east-2.aws.neon.tech", "NAME": "synthetic_example", "PORT": ""}
        with patch.dict(settings.DATABASES, {"default": db}):
            direct = artifact_dir(run)
        with patch.dict(settings.DATABASES, {"default": {**db, "HOST": "ep-example-pooler.c-7.us-east-2.aws.neon.tech", "PORT": "5432"}}):
            pooled = artifact_dir(run)
        with patch.dict(settings.DATABASES, {"default": {**db, "HOST": "ep-other.c-7.us-east-2.aws.neon.tech"}}):
            other_branch = artifact_dir(run)
        self.assertEqual(direct, pooled)
        self.assertNotEqual(direct, other_branch)

    def test_public_json_finite_and_identity_guards(self):
        self.assertEqual(public_json({"metric": float("nan")}), {"metric": None})
        with self.assertRaises(ValueError):
            public_json({"patient_key": "private"})
