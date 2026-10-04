from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .dashboard import blood_pressure, blood_sugar
from .models import (
    AuditEvent,
    ClinicalEntry,
    DispenseEvent,
    DispenseItem,
    MedicalRecord,
    MedicalReport,
    Patient,
    Prescription,
    PrescriptionItem,
    ProviderApplication,
)


class PatientDashboardTests(TestCase):
    endpoint = "/api/v1/patients/me/dashboard/"

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(
            "dashboard@example.test", name="Patient", email_verified_at=timezone.now()
        )
        cls.other = User.objects.create_user(
            "other@example.test",
            name="Another patient",
            email_verified_at=timezone.now(),
        )
        cls.patient = Patient.objects.create(user=cls.owner)
        cls.other_patient = Patient.objects.create(user=cls.other)
        cls.doctor = User.objects.create_user(
            "doctor@example.test",
            name="Doctor One",
            role="doctor",
            email_verified_at=timezone.now(),
        )
        cls.pharmacy = User.objects.create_user(
            "pharmacy@example.test",
            name="Pharmacy",
            role="pharmacist",
            email_verified_at=timezone.now(),
        )
        cls.admin = User.objects.create_superuser("admin@example.test", name="Admin")
        cls.doctor_app = ProviderApplication.objects.create(
            provider=cls.doctor,
            version=1,
            registration_number="DOCTOR",
            registering_body="Test council",
            practice_address="Test clinic",
        )
        cls.pharmacy_app = ProviderApplication.objects.create(
            provider=cls.pharmacy,
            version=1,
            registration_number="PHARMACY",
            registering_body="Test council",
            practice_address="Test pharmacy",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def get_dashboard(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def record(self, vitals=None, patient=None, **kwargs):
        return MedicalRecord.objects.create(
            patient=patient or self.patient,
            doctor=self.doctor,
            complaint="Check-up",
            vitals=vitals or {},
            **kwargs,
        )

    def prescription(self, *, patient=None, remaining=10, **kwargs):
        rx = Prescription.objects.create(
            patient=patient or self.patient,
            doctor=self.doctor,
            application=self.doctor_app,
            valid_until=kwargs.pop("valid_until", timezone.now() + timedelta(days=5)),
            **kwargs,
        )
        item = PrescriptionItem.objects.create(
            prescription=rx,
            medicine="Test medicine",
            dosage="Test directions",
            quantity=Decimal(10),
            unit="tablet",
        )
        if remaining != 10:
            event = DispenseEvent.objects.create(
                prescription=rx,
                pharmacist=self.pharmacy,
                application=self.pharmacy_app,
                idempotency_key=str(rx.id),
                payload_digest="test",
                patient_name="Patient",
                patient_health_id="test",
                pharmacist_name="Pharmacy",
                shop_name="Test pharmacy",
            )
            DispenseItem.objects.create(
                event=event,
                prescription_item=item,
                quantity=Decimal(10 - remaining),
                unit="tablet",
                medicine=item.medicine,
            )
        return rx, item

    def test_requires_verified_patient_account(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(self.endpoint).status_code, (401, 403))
        for user in [self.doctor, self.pharmacy, self.admin]:
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.get(self.endpoint).status_code, 403)
        self.owner.email_verified_at = None
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.get(self.endpoint).status_code, 403)

    def test_empty_history_has_unknown_metrics_and_no_invented_alerts(self):
        data = self.get_dashboard()
        self.assertEqual(
            data["counts"],
            {
                "records": 0,
                "active_prescriptions": 0,
                "conditions": 0,
                "reports": 0,
                "report_downloads": 0,
            },
        )
        self.assertEqual(data["trends"], {"blood_pressure": [], "blood_sugar": []})
        self.assertEqual(data["latest"], {"blood_pressure": None, "blood_sugar": None})
        for key in ("health_score", "risk_level", "adherence"):
            self.assertIsNone(data[key])
        self.assertEqual(data["lab_summary"], {"abnormal": None, "total": None})
        self.assertEqual(data["regional_alerts"], {"available": False, "items": []})
        self.assertEqual(data["recent_notifications"], [])
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.owner, patient=self.patient, event="dashboard.read"
            ).exists()
        )
        response = self.client.get(self.endpoint)
        self.assertIn("no-store", response["Cache-Control"])

    def test_data_is_owned_even_when_another_patient_id_is_supplied(self):
        other_record = self.record(
            {"blood_pressure": "145/90", "glucose_mg_dl": "150"},
            patient=self.other_patient,
        )
        MedicalReport.objects.create(
            patient=self.other_patient,
            uploaded_by=self.other,
            name="private.pdf",
            title="Other private report",
            storage_name="private",
            content_type="application/pdf",
            size_bytes=10,
        )
        self.prescription(patient=self.other_patient)
        ClinicalEntry.objects.create(
            patient=self.other_patient,
            author=self.doctor,
            kind="condition",
            name="Other private condition",
            source="clinician_recorded",
        )
        AuditEvent.objects.create(
            actor=self.owner, patient=self.other_patient, event="report.download"
        )
        response = self.client.get(
            self.endpoint, {"patient_id": str(self.other_patient.id)}
        )
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertTrue(all(value == 0 for value in data["counts"].values()))
        self.assertEqual(data["recent_notifications"], [])
        self.assertNotIn(str(other_record.id), str(data))

    def test_counts_cover_all_records_and_active_conditions_and_own_downloads(self):
        MedicalRecord.objects.bulk_create(
            [
                MedicalRecord(
                    patient=self.patient, doctor=self.doctor, complaint=f"Visit {i}"
                )
                for i in range(55)
            ]
        )
        ClinicalEntry.objects.create(
            patient=self.patient,
            author=self.doctor,
            kind="condition",
            name="Active",
            source="clinician_recorded",
        )
        ClinicalEntry.objects.create(
            patient=self.patient,
            author=self.doctor,
            kind="condition",
            name="Resolved",
            source="clinician_recorded",
            resolved_at=timezone.now(),
        )
        ClinicalEntry.objects.create(
            patient=self.patient,
            author=self.doctor,
            kind="allergy",
            name="Allergy",
            source="clinician_recorded",
        )
        MedicalReport.objects.create(
            patient=self.patient,
            uploaded_by=self.owner,
            name="report.pdf",
            storage_name="own-report",
            content_type="application/pdf",
            size_bytes=10,
        )
        for actor, event, outcome in [
            (self.owner, "report.download", "success"),
            (self.owner, "report.download", "success"),
            (self.doctor, "report.download", "success"),
            (self.owner, "report.download", "denied"),
            (self.owner, "prescription.download", "success"),
        ]:
            AuditEvent.objects.create(
                actor=actor, patient=self.patient, event=event, outcome=outcome
            )
        counts = self.get_dashboard()["counts"]
        self.assertEqual(counts["records"], 55)
        self.assertEqual(counts["conditions"], 1)
        self.assertEqual(counts["reports"], 1)
        self.assertEqual(counts["report_downloads"], 2)

    def test_active_prescriptions_exclude_expired_cancelled_and_fulfilled(self):
        self.prescription()
        partial_rx, item = self.prescription(remaining=4)
        self.prescription(remaining=0)
        self.prescription(valid_until=timezone.now() - timedelta(seconds=1))
        self.prescription(cancelled_at=timezone.now())
        # A second fully dispensed item must not duplicate or suppress the partial Rx.
        extra_item = PrescriptionItem.objects.create(
            prescription=partial_rx,
            medicine="Extra",
            dosage="Test",
            quantity=Decimal(2),
            unit="tablet",
        )
        event = DispenseEvent.objects.get(prescription=partial_rx)
        DispenseItem.objects.create(
            event=event,
            prescription_item=extra_item,
            quantity=Decimal(2),
            unit="tablet",
            medicine="Extra",
        )
        Prescription.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            application=self.doctor_app,
            valid_until=timezone.now() + timedelta(days=5),
        )
        self.assertEqual(self.get_dashboard()["counts"]["active_prescriptions"], 2)
        second_event = DispenseEvent.objects.create(
            prescription=partial_rx,
            pharmacist=self.pharmacy,
            application=self.pharmacy_app,
            idempotency_key="second",
            payload_digest="test",
            patient_name="Patient",
            patient_health_id="test",
            pharmacist_name="Pharmacy",
            shop_name="Test pharmacy",
        )
        DispenseItem.objects.create(
            event=second_event,
            prescription_item=item,
            quantity=Decimal(4),
            unit="tablet",
            medicine=item.medicine,
        )
        self.assertEqual(self.get_dashboard()["counts"]["active_prescriptions"], 1)

    def test_trends_are_latest_twenty_four_valid_readings_chronological(self):
        base = timezone.now() - timedelta(days=32)
        rows = []
        for i in range(27):
            row = self.record(
                {
                    "blood_pressure": f" {110 + i} / 75 mmHg ",
                    "glucose_mg_dl": 100 + i,
                    "glucose_context": "fasting",
                }
            )
            MedicalRecord.objects.filter(pk=row.pk).update(
                created_at=base + timedelta(days=i)
            )
            rows.append(row)
        self.record({"blood_pressure": "0/80", "glucose_mg_dl": "NaN"})
        data = self.get_dashboard()
        pressure = data["trends"]["blood_pressure"]
        glucose = data["trends"]["blood_sugar"]
        self.assertEqual(len(pressure), 24)
        self.assertEqual([r["systolic"] for r in pressure], list(range(113, 137)))
        self.assertEqual([r["value"] for r in glucose], list(range(103, 127)))
        self.assertEqual(pressure[-1]["record_id"], str(rows[-1].id))
        self.assertEqual(pressure[-1]["author"], self.doctor.name)
        self.assertEqual(pressure[-1]["source"], "Consultation")
        self.assertEqual(glucose[-1]["context"], "fasting")
        self.assertEqual(data["latest"]["blood_pressure"], pressure[-1])
        self.assertEqual(data["latest"]["blood_sugar"], glucose[-1])
        self.assertLess(pressure[0]["recorded_at"], pressure[-1]["recorded_at"])

    def test_corrections_supersede_original_vitals_but_remain_in_record_count(self):
        original = self.record({"blood_pressure": "160/100", "glucose": "160 mg/dL"})
        correction = self.record(
            {"blood_pressure": "130/80", "glucose": "130 mg/dL"},
            correction_of=original,
            correction_reason="Correct reading",
        )
        final = self.record(
            {"systolic": 120, "diastolic": 75, "blood_sugar": 110},
            correction_of=correction,
            correction_reason="Confirm reading",
        )
        data = self.get_dashboard()
        self.assertEqual(data["counts"]["records"], 3)
        self.assertEqual(
            [row["record_id"] for row in data["trends"]["blood_pressure"]],
            [str(final.id)],
        )
        self.assertEqual([row["value"] for row in data["trends"]["blood_sugar"]], [110])
        self.record(
            {}, correction_of=final, correction_reason="Remove unsupported measurements"
        )
        data = self.get_dashboard()
        self.assertIsNone(data["latest"]["blood_pressure"])
        self.assertIsNone(data["latest"]["blood_sugar"])

    def test_parsing_rejects_invalid_values_and_respects_units(self):
        for value in (None, "0/80", "120/0", "-20/80", "NaN/80", "120/80 kPa", "text"):
            self.assertIsNone(blood_pressure({"blood_pressure": value}))
        for value in (
            False,
            True,
            None,
            0,
            -10,
            "NaN",
            float("inf"),
            "120 mmol/L",
            [],
            {},
        ):
            self.assertIsNone(blood_sugar({"glucose_mg_dl": value}))
        self.assertEqual(
            blood_pressure({"blood_pressure": " 120 / 80 MM HG "}),
            {"systolic": 120, "diastolic": 80, "unit": "mmHg"},
        )
        self.assertEqual(blood_sugar({"glucose": " 120.5 mg/dL "})["value"], 120.5)

    def test_notifications_include_latest_five_own_events_with_working_destinations(
        self,
    ):
        for i in range(6):
            self.record({})
        report = MedicalReport.objects.create(
            patient=self.patient,
            uploaded_by=self.owner,
            name="report.pdf",
            title="Latest lab",
            storage_name="latest-report",
            content_type="application/pdf",
            size_bytes=10,
        )
        rx, _ = self.prescription()
        base = timezone.now()
        MedicalRecord.objects.filter(patient=self.patient).update(
            created_at=base - timedelta(days=2)
        )
        MedicalReport.objects.filter(pk=report.pk).update(
            created_at=base - timedelta(days=1)
        )
        Prescription.objects.filter(pk=rx.pk).update(created_at=base)
        notifications = self.get_dashboard()["recent_notifications"]
        self.assertEqual(len(notifications), 5)
        self.assertEqual(notifications[0]["id"], f"prescription:{rx.id}")
        self.assertEqual(notifications[1]["id"], f"report:{report.id}")
        self.assertEqual(notifications[1]["title"], "Report uploaded: Latest lab")
        self.assertEqual(
            [row["target_tab"] for row in notifications],
            ["prescriptions", "reports", "records", "records", "records"],
        )
        self.assertEqual(len({row["id"] for row in notifications}), 5)

    @override_settings(
        HEALTH_SCORE_POLICY={
            "method": "Synthetic test-only method",
            "version": "test",
            "label": "Synthetic score",
            "components": [
                {
                    "key": "systolic",
                    "label": "Pressure",
                    "weight": 1,
                    "max_age_days": 30,
                    "rules": [{"upper_bound": None, "score": 70}],
                }
            ],
            "risk_bands": [{"min_score": 0, "label": "Synthetic band"}],
        }
    )
    def test_recent_correction_keeps_original_measurement_date_and_stays_stale(self):
        original = self.record({"blood_pressure": "120/80"})
        old_date = timezone.now() - timedelta(days=365)
        MedicalRecord.objects.filter(pk=original.pk).update(created_at=old_date)
        correction = self.record(
            {"blood_pressure": "120/80"},
            correction_of=original,
            correction_reason="Notes corrected",
        )
        terminal = self.record(
            {"blood_pressure": "122/80"},
            correction_of=correction,
            correction_reason="Measurement corrected",
        )
        data = self.get_dashboard()
        self.assertEqual(
            data["latest"]["blood_pressure"]["recorded_at"], old_date.isoformat()
        )
        self.assertEqual(
            data["latest"]["blood_pressure"]["record_id"], str(terminal.id)
        )
        self.assertIsNone(data["health_score"])
        self.assertIn("recent observation", data["health_score_reason"])

    def test_old_consultation_corrected_today_is_not_one_of_latest_twenty_four_readings(
        self,
    ):
        original = self.record({"blood_pressure": "140/90", "glucose_mg_dl": 160})
        MedicalRecord.objects.filter(pk=original.pk).update(
            created_at=timezone.now() - timedelta(days=365)
        )
        recent_ids = []
        for i in range(24):
            row = self.record({"blood_pressure": "120/80", "glucose_mg_dl": 100})
            MedicalRecord.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(days=24 - i)
            )
            recent_ids.append(str(row.id))
        self.record(
            {"blood_pressure": "130/85", "glucose_mg_dl": 150},
            correction_of=original,
            correction_reason="Correct historical note",
        )
        data = self.get_dashboard()
        for key in ("blood_pressure", "blood_sugar"):
            self.assertEqual(
                [row["record_id"] for row in data["trends"][key]], recent_ids
            )
