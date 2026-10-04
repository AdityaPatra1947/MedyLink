"""Reproducibility and append-only application, using Django's isolated test DB."""

import json
from collections import Counter
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from accounts.models import User
from clinic.models import LabResult, MedicalRecord, Patient, ProviderApplication
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from .models import (
    DatasetBatch,
    DiseaseObservation,
    PatientAreaObservation,
    StationArea,
)
from .synthetic_generation import (
    END,
    START,
    SYMPTOMS,
    WEIGHTS,
    append_synthetic_patients,
    generate_patients,
)


def stations():
    reference = Path(__file__).resolve().parents[2] / "data/reference/mumbai_stations.json"
    rows = json.loads(reference.read_text(encoding="utf-8"))["stations"]
    return [{"key": row["station_id"], "name": row["station_name"], "latitude": row["latitude"], "longitude": row["longitude"]} for row in rows]


class GeneratedPatientTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows = generate_patients(3000, 42, stations())

    def test_patient_counts_classes_stations_and_full_history(self):
        self.assertEqual(len(self.rows), 3000)
        self.assertEqual(len({row["id"] for row in self.rows}), 3000)
        self.assertEqual(len({row["station_key"] for row in self.rows}), 34)
        counts = Counter(row["visits"][0]["primary_disease_code"] for row in self.rows)
        self.assertEqual(set(counts), set(WEIGHTS))
        self.assertGreaterEqual(min(counts.values()), 90)
        self.assertNotEqual(len(set(counts.values())), 1)
        dates = [datetime.fromisoformat(visit["observed_at"]).date() for row in self.rows for visit in row["visits"]]
        self.assertEqual((min(dates), max(dates)), (START, END))
        self.assertTrue(all(2 <= len(row["visits"]) <= 4 for row in self.rows))
        secondary = sum(bool(row["visits"][0]["secondary_disease_codes"]) for row in self.rows)
        self.assertTrue(.12 <= secondary / len(self.rows) <= .18)

    def test_reproducibility_seed_change_and_append_prefix(self):
        same = generate_patients(60, 42, list(reversed(stations())))
        self.assertEqual(same, self.rows[:60])
        other = generate_patients(60, 43, stations())
        self.assertNotEqual(same, other)
        self.assertFalse({row["id"] for row in same} & {row["id"] for row in other})

    def test_missingness_measurements_and_symptoms_are_not_fabricated_as_zero(self):
        keys = ("temperature_c", "systolic", "diastolic", "glucose_mg_dl", "hemoglobin", "spo2", "heart_rate_bpm", "platelets")
        missing, total = 0, 0
        for row in self.rows:
            dob = date.fromisoformat(row["date_of_birth"])
            for visit in row["visits"]:
                values = visit["vitals"]
                observed = datetime.fromisoformat(visit["observed_at"]).date()
                self.assertGreater((observed - dob).days, 16 * 365)
                self.assertEqual(values["primary_disease_code"], visit["primary_disease_code"])
                self.assertTrue(values["synthetic"])
                self.assertEqual(set(values["symptoms"]), set(SYMPTOMS))
                self.assertTrue(all(value in {0, 1, None} for value in values["symptoms"].values()))
                cells = [values[key] for key in keys] + list(values["symptoms"].values())
                missing += cells.count(None)
                total += len(cells)
                if values["systolic"] is None or values["diastolic"] is None:
                    self.assertNotIn("blood_pressure", values)
        self.assertTrue(.045 < missing / total < .055)

    def test_disease_patterns_have_overlap_and_geographic_seasonal_signal(self):
        visits = [visit for row in self.rows for visit in row["visits"]]
        dengue = [visit for visit in visits if visit["primary_disease_code"] == "DENGUE"]
        platelets = [visit["vitals"]["platelets"] for visit in dengue if visit["vitals"]["platelets"] is not None]
        fraction = sum(value < 150000 for value in platelets) / len(platelets)
        self.assertTrue(.7 < fraction < .99)  # Learnable, with noisy counterexamples.
        self.assertGreater(sum(datetime.fromisoformat(visit["observed_at"]).month in {7, 8, 9, 10} for visit in dengue) / len(dengue), .55)
        dengue_patients = [row for row in self.rows if row["visits"][0]["primary_disease_code"] == "DENGUE"]
        self.assertGreater(sum(row["station_key"] in {"KURLA", "VASHI", "ANDHERI"} for row in dengue_patients) / len(dengue_patients), .40)

    def test_invalid_input_is_rejected(self):
        for count, seed in ((0, 42), (5001, 42), (10, -1), (True, 42)):
            with self.assertRaises(ValueError):
                generate_patients(count, seed, stations())


class SyntheticAppendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.batch = DatasetBatch.objects.create(key="mumbai_stations_v1", synthetic=True, generator_version="original", seed=1, as_of=date(2026, 9, 29), observation_start=date(2026, 9, 1), manifest_hash="a" * 64, dataset_hash="b" * 64, input_hashes={"manifest": "old"}, patient_count=1000, observation_count=2000)
        StationArea.objects.bulk_create([StationArea(batch=cls.batch, key=row["key"], name=row["name"], latitude=row["latitude"], longitude=row["longitude"]) for row in stations()])
        cls.doctor = User.objects.create_user(email="doctor@synthetic.invalid", name="Synthetic Doctor", role="doctor")
        ProviderApplication.objects.create(provider=cls.doctor, version=1, is_current=True, status="approved", registration_number="SYNTH-TEST", registering_body="Simulated", practice_address="Simulated")
        cls.existing = Patient.objects.create(user=User.objects.create_user(email="existing@synthetic.invalid", name="Existing Patient"))
        cls.original = MedicalRecord.objects.create(patient=cls.existing, doctor=cls.doctor, complaint="Existing complaint", diagnosis="Existing diagnosis", vitals={"systolic": 125})

    def generate(self, count=20, seed=42):
        # Patches only the target guard: ORM writes use the temporary test DB.
        with patch("clinic.management.commands.import_synthetic_dataset.Command.require_target"):
            return append_synthetic_patients(count, seed)

    def test_counts_idempotence_timestamps_and_existing_data_are_preserved(self):
        before = DatasetBatch.objects.values().get(pk=self.batch.pk)
        original = MedicalRecord.objects.values().get(pk=self.original.pk)
        generated = self.generate()
        self.assertEqual(generated["created_patients"], 20)
        self.assertEqual(Patient.objects.count(), 21)
        self.assertEqual(PatientAreaObservation.objects.count(), 20)
        self.assertEqual(MedicalRecord.objects.count(), 1 + generated["created_visits"])
        self.assertEqual(LabResult.objects.count(), generated["created_labs"])
        self.assertTrue(DiseaseObservation.objects.exists())
        repeat = self.generate()
        self.assertEqual(repeat["created_patients"], 0)
        self.assertEqual(repeat["existing_patients"], 20)
        self.assertEqual(Patient.objects.count(), 21)
        self.assertEqual(DatasetBatch.objects.values().get(pk=self.batch.pk), before)
        self.assertEqual(MedicalRecord.objects.values().get(pk=self.original.pk), original)
        self.assertTrue(all(not row.has_usable_password() and not row.is_active for row in User.objects.filter(email__endswith="@patients.medylink.invalid")))
        for observation in DiseaseObservation.objects.select_related("medical_record"):
            self.assertEqual(observation.observed_at, observation.medical_record.created_at)
            self.assertTrue(START <= observation.observed_at.date() <= END)
        self.assertFalse(LabResult.objects.exclude(created_at__lte=datetime(2026, 10, 1, tzinfo=datetime.fromisoformat("2026-01-01T00:00:00+00:00").tzinfo)).exists())
        for lab in LabResult.objects.all():
            self.assertEqual(lab.measured_at, lab.created_at)

    def test_increased_count_only_adds_new_patients(self):
        self.generate(12)
        previous = list(MedicalRecord.objects.exclude(pk=self.original.pk).order_by("id").values())
        result = self.generate(20)
        self.assertEqual(result["created_patients"], 8)
        self.assertEqual(PatientAreaObservation.objects.count(), 20)
        self.assertEqual(list(MedicalRecord.objects.filter(id__in=[row["id"] for row in previous]).order_by("id").values()), previous)

    @override_settings(SYNTHETIC_IMPORT_ALLOWED=False)
    def test_command_refuses_normal_database_before_any_query(self):
        with self.assertNumQueries(0), self.assertRaises(CommandError):
            call_command("generate_synthetic_data", count=20, seed=42, stdout=StringIO())

    def test_command_reports_created_and_already_present_counts(self):
        output = StringIO()
        with patch("clinic.management.commands.import_synthetic_dataset.Command.require_target"):
            call_command("generate_synthetic_data", count=10, seed=42, stdout=output)
            call_command("generate_synthetic_data", count=10, seed=42, stdout=output)
        self.assertIn("Created 10 synthetic patients", output.getvalue())
        self.assertIn("10 already present", output.getvalue())
