"""Disease filters, snapshot boundaries, and independent model-task storage."""

from datetime import date, datetime, timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch

from accounts.models import User
from clinic.models import LabResult, MedicalRecord, Patient
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .ml_dataset import build_dataset
from .ml_services import artifact_dir, enqueue_training, execute_training
from .models import DatasetBatch, MLRun, PatientAreaObservation, StationArea


@override_settings(SYNTHETIC_IMPORT_ALLOWED=True)
class DiseaseMLTests(TestCase):
    def setUp(self):
        self.at = datetime(2026, 7, 15, 10, tzinfo=timezone.utc)
        self.admin = User.objects.create_user(email="admin@disease.test", password="Test-only!123", name="Synthetic admin", role="admin", email_verified_at=self.at)
        self.doctor = User.objects.create_user(email="doctor@disease.test", name="Synthetic doctor", role="doctor", email_verified_at=self.at)
        self.batch = DatasetBatch.objects.create(key="disease_test", seed=42, synthetic=True, generator_version="test", as_of=date(2026, 9, 30), observation_start=date(2024, 10, 31), manifest_hash="a" * 64, dataset_hash="b" * 64, patient_count=13, observation_count=13)
        self.stations = [StationArea.objects.create(batch=self.batch, key=key, name=name, lines=lines, latitude=lat, longitude=lon) for key, name, lines, lat, lon in [("KURLA", "Kurla", ["Central", "Harbour"], 19.06, 72.88), ("ANDHERI", "Andheri", ["Western", "Harbour"], 19.12, 72.84)]]
        self.records = []
        for index in range(13):
            user = User.objects.create_user(email=f"patient{index}@disease.test", name="Synthetic patient", role="patient")
            patient = Patient.objects.create(user=user, date_of_birth=date(1980, 1, 1), gender="female")
            station = self.stations[0 if index < 6 else 1]
            PatientAreaObservation.objects.create(batch=self.batch, patient=patient, source_key=f"TEST-{index}", station=station, latitude=station.latitude, longitude=station.longitude, coordinate_source="synthetic", valid_at=self.at.date())
            diagnosis = "Asthma and Dengue" if index == 0 else "Asthma" if index < 6 else "Dengue" if index < 11 else "Influenza"
            record = MedicalRecord.objects.create(patient=patient, doctor=self.doctor, diagnosis=diagnosis, complaint="Private text", vitals={"systolic": 125, "diastolic": 80, "temperature_c": 38, "hemoglobin": 12, "spo2": 96, "platelets": 180000, "symptoms": {"cough": 1, "fever": 0}})
            MedicalRecord.objects.filter(pk=record.pk).update(created_at=self.at)
            self.records.append(record)
        self.filters = {"dataset_id": self.batch.key, "date_from": None, "date_to": None, "disease_code": "", "station_id": "", "line": ""}
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def insights(self, **extra):
        with patch("analytics.ml_services.pipeline") as learner, patch("analytics.ml_services.current_hotspots", return_value={"clusters": []}):
            learner.return_value.cluster_patient_groups.return_value = {"status": "insufficient_data", "groups": []}
            response = self.client.get("/api/v1/admin/analytics/ml/insights/", {"dataset_id": self.batch.key, **extra})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_multi_disease_or_filter_deduplicates_patients_and_station_cells(self):
        body = self.insights(disease_codes="ASTHMA,DENGUE")
        self.assertEqual(body["source"]["patients"], 11)
        self.assertEqual({row["code"]: row["count"] for row in body["summary"]["disease_counts"]}, {"ASTHMA": 6, "DENGUE": 6})
        stations = {row["station_id"]: row for row in body["summary"]["station_disease_counts"]}
        self.assertEqual(stations["KURLA"]["patient_count"], 6)
        self.assertEqual(stations["ANDHERI"]["patient_count"], 5)
        kurla = {row["code"]: row["count"] for row in stations["KURLA"]["diseases"]}
        self.assertEqual(kurla, {"ASTHMA": 6, "DENGUE": None})
        self.assertEqual(body["disease"]["source"]["patients"], 10)  # Ambiguous primary label excluded.

    def test_partial_case_insensitive_search_and_empty_search_result(self):
        body = self.insights(disease_search="aStH")
        self.assertEqual(body["source"]["patients"], 6)
        self.assertEqual(body["summary"]["disease_counts"], [{"code": "ASTHMA", "label": "Asthma", "count": 6}])
        self.assertEqual(self.insights(disease_search="not-a-condition")["source"]["patients"], 0)
        self.assertEqual(self.insights(disease_codes="DENGUE", disease_search="asth")["source"]["patients"], 0)

    def test_filters_combine_with_station_dates_and_clear(self):
        self.assertEqual(self.insights(disease_codes="ASTHMA,DENGUE", station_id="ANDHERI")["source"]["patients"], 5)
        self.assertEqual(self.insights(disease_codes="ASTHMA", date_to="2026-06-30")["source"]["patients"], 0)
        self.assertEqual(self.insights(disease_codes="")["source"]["patients"], 13)
        self.assertIsNone(self.insights(disease_search="flu")["source"]["patients"])

    def test_filter_validation_and_role_permissions(self):
        for invalid in [{"disease_codes": "ASTHMA,INVALID"}, {"disease_codes": "ASTHMA,,DENGUE"}, {"disease_search": "x" * 81}]:
            self.assertEqual(self.client.get("/api/v1/admin/analytics/ml/insights/", {"dataset_id": self.batch.key, **invalid}).status_code, 400)
        self.client.force_authenticate(self.doctor)
        self.assertEqual(self.client.get("/api/v1/admin/analytics/ml/insights/", {"dataset_id": self.batch.key, "disease_codes": "ASTHMA"}).status_code, 403)

    def test_new_features_are_visit_snapshots_not_later_correction_values(self):
        original = self.records[1]
        correction = MedicalRecord.objects.create(patient=original.patient, doctor=self.doctor, correction_of=original, diagnosis="Malaria", vitals={"hemoglobin": 8, "symptoms": {"cough": 0, "fever": 1}})
        MedicalRecord.objects.filter(pk=correction.pk).update(created_at=datetime(2026, 8, 15, tzinfo=timezone.utc))
        data = build_dataset(self.batch, self.filters)
        before = [r for r in data["history"] if r["primary_disease"] == "ASTHMA"]
        self.assertTrue(before)
        self.assertTrue(all(r["hemoglobin"] == 12 and r["cough"] == 1 for r in before))
        self.assertTrue(all(r["rash"] is None for r in before))
        self.assertTrue(all(r["synthetic"] and r["month"] == 7 for r in before))

    def test_malformed_primary_label_does_not_break_legacy_visits(self):
        for malformed in ([], {}, 7):
            row = self.records[1]
            MedicalRecord.objects.filter(pk=row.pk).update(vitals={"primary_disease_code": malformed, "blood_pressure": "125/80"})
            data = build_dataset(self.batch, self.filters)
            self.assertEqual(len(data["cohort"]), 13)

    def test_generated_missing_measurements_stay_missing_until_pipeline(self):
        row = self.records[1]
        MedicalRecord.objects.filter(pk=row.pk).update(vitals={"synthetic": True, "generator": "disease_v1", "primary_disease_code": "ASTHMA", "systolic": 125, "diastolic": None, "glucose_mg_dl": None})
        previous = datetime(2026, 7, 14, 10, tzinfo=timezone.utc)
        lab = LabResult.objects.create(patient=row.patient, recorded_by=self.doctor, name="Fasting glucose", value=150, unit="mg/dL", measured_at=previous)
        LabResult.objects.filter(pk=lab.pk).update(created_at=previous)
        data = build_dataset(self.batch, self.filters)
        generated = [r for r in data["history"] if r["systolic"] == 125 and r["diastolic"] is None]
        self.assertEqual(len(generated), 1)
        self.assertIsNone(generated[0]["glucose"])

    def test_task_runs_are_independent_and_failure_preserves_other_task(self):
        bp = MLRun.objects.create(batch=self.batch, actor=self.admin, task="blood_pressure", status="completed", is_active_model=True)
        disease = MLRun.objects.create(batch=self.batch, actor=self.admin, task="disease", status="completed", is_active_model=True)
        run, reused = enqueue_training(self.batch, self.admin, self.filters, task="disease", asynchronous=False)
        self.assertFalse(reused)
        repeated, reused = enqueue_training(self.batch, self.admin, self.filters, task="disease", asynchronous=False)
        self.assertTrue(reused)
        self.assertEqual(run.pk, repeated.pk)
        with TemporaryDirectory() as directory, override_settings(ML_ARTIFACT_ROOT=directory):
            def train(rows, target):
                self.assertEqual(len(rows), 13)
                target.mkdir(parents=True)
                (target / "model_bundle.joblib").write_bytes(b"test-placeholder")
                return {"status": "completed", "task": "disease", "selection": {"prediction_enabled": False}}
            with patch("analytics.ml_services.close_old_connections"), patch("analytics.ml_services.disease_pipeline") as learner:
                learner.return_value.train_and_evaluate.side_effect = train
                completed = execute_training(run.id)
        bp.refresh_from_db()
        disease.refresh_from_db()
        self.assertTrue(bp.is_active_model)
        self.assertFalse(disease.is_active_model)
        self.assertTrue(completed.is_active_model)
        self.assertEqual(completed.task, "disease")
        self.assertNotEqual(artifact_dir(bp), artifact_dir(completed))

    def test_post_and_list_task_routes_reuse_existing_storage(self):
        response = self.client.post("/api/v1/admin/analytics/ml/runs/", {**self.filters, "task": "disease", "disease_codes": "ASTHMA,DENGUE"}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        run = MLRun.objects.get(pk=response.data["id"])
        self.assertEqual(run.task, "disease")
        self.assertNotIn("task", run.filters)
        result = self.client.get("/api/v1/admin/analytics/ml/runs/", {"dataset_id": self.batch.key, "task": "disease"})
        self.assertEqual(len(result.data["runs"]), 1)
        self.assertEqual(self.client.get("/api/v1/admin/analytics/ml/runs/", {"dataset_id": self.batch.key}).data["runs"], [])
        self.assertEqual(self.client.post("/api/v1/admin/analytics/ml/runs/", {**self.filters, "task": "invalid"}, format="json").status_code, 400)
