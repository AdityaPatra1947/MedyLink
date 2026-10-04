"""Report provenance, isolation, transactionality and independent score arithmetic."""

import io
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from reportlab.pdfgen.canvas import Canvas
from rest_framework.exceptions import ValidationError

from .dashboard import dashboard_data
from .models import AuditEvent, ClinicalEntry, LabResult, MedicalRecord, MedicalReport, MedicationAdherenceLog, Patient, Prescription, PrescriptionItem
from .report_extraction import FRIENDLY_FIELDS, extract_report_observations, parse_monthly_pdf
from .report_formats import MONTHLY_END, MONTHLY_FORMAT, MONTHLY_START
from .tests import ClinicFixtures


@override_settings(SYNTHETIC_REPORT_EXTRACTION_ALLOWED=True, SYNTHETIC_REPORT_SCORE_ENABLED=True)
class MonthlyReportTests(ClinicFixtures, TestCase):
    def setUp(self):
        self.setup_domain()
        self.other_patient = Patient.objects.create(user=self.other)
        (settings.BASE_DIR.parent / ".local").mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=settings.BASE_DIR.parent / ".local")
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(PRIVATE_MEDIA_ROOT=Path(self.temp.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.measured = timezone.now() - timedelta(minutes=1)
        self.today = self.measured.date()

    def lines(self):
        return [
            "AROGYATRACK_MONTHLY_V1", f"Report-ID: AT-DEMO-PAT0001-{self.measured:%Y%m}",
            f"Patient-Account-ID: {self.owner.account_id}", f"Doctor-Account-ID: {self.doctor.account_id}",
            f"Measured-At: {self.measured.isoformat()}", "Systolic-mmHg: 128", "Diastolic-mmHg: 82",
            "Fasting-Glucose-mg-dL: 104", f"Adherence-Period-Start: {self.today - timedelta(days=6)}",
            f"Adherence-Period-End: {self.today}",
            *[f"Dose-Day: {self.today - timedelta(days=i)}|4|3" for i in range(6, -1, -1)],
            "END_AROGYATRACK_MONTHLY_V1",
        ]

    def pdf(self, lines=None):
        data = io.BytesIO()
        canvas = Canvas(data)
        text = canvas.beginText(30, 800)
        text.setFont("Helvetica", 9)
        for line in self.lines() if lines is None else lines:
            text.textLine(line)
        canvas.drawText(text)
        canvas.save()
        return data.getvalue()

    def upload(self, user=None, lines=None):
        return self.as_user(user or self.doctor).post(
            f"/api/v1/patients/{self.patient.pk}/reports/",
            {"title": "Monthly fixture", "record_id": str(self.record.pk),
             "file": SimpleUploadedFile("monthly.pdf", self.pdf(lines), content_type="application/pdf")},
            format="multipart",
        )

    def test_friendly_and_original_visible_fields_extract_identically(self):
        original = parse_monthly_pdf(io.BytesIO(self.pdf()), self.patient, self.doctor)
        names = {value: key for key, value in FRIENDLY_FIELDS.items()}
        friendly = []
        for line in self.lines():
            key, separator, value = line.partition(":")
            if key == "Dose-Day":
                friendly.append(value.strip().replace("|", "  |  "))
            elif key in names:
                friendly.append(names[key] + ":" + value)
            else:
                friendly.append(line)
        self.assertEqual(parse_monthly_pdf(io.BytesIO(self.pdf(friendly)), self.patient, self.doctor), original)

    def test_current_and_legacy_report_branding_preserve_measurements(self):
        legacy = parse_monthly_pdf(io.BytesIO(self.pdf()), self.patient, self.doctor)
        lines = self.lines()
        lines[0], lines[-1] = MONTHLY_START, MONTHLY_END
        lines[1] = lines[1].replace("AT-DEMO-", "ML-DEMO-")
        current = parse_monthly_pdf(io.BytesIO(self.pdf(lines)), self.patient, self.doctor)
        self.assertEqual(current["format"], MONTHLY_FORMAT)
        self.assertEqual(legacy["format"], "arogyatrack-monthly-v1")
        for key in ("blood_pressure", "blood_sugar", "adherence", "measured_at"):
            self.assertEqual(current[key], legacy[key])
        response = self.upload(lines=lines)
        self.assertEqual(response.status_code, 201, response.data)
        dashboard = dashboard_data(self.patient, self.owner)
        self.assertEqual(len(dashboard["trends"]["blood_pressure"]), 1)
        self.assertEqual(dashboard["trends"]["blood_pressure"][0]["systolic"], 128)
        self.assertIsNotNone(dashboard["health_score"])

    def test_mixed_brand_measurement_block_is_rejected(self):
        lines = self.lines()
        lines[0] = MONTHLY_START
        with self.assertRaises(ValidationError):
            parse_monthly_pdf(io.BytesIO(self.pdf(lines)), self.patient, self.doctor)
        lines[-1] = MONTHLY_END
        lines.extend(self.lines())
        with self.assertRaises(ValidationError):
            parse_monthly_pdf(io.BytesIO(self.pdf(lines)), self.patient, self.doctor)

    def test_upload_extracts_only_glucose_lab_and_report_linked_doses(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.data)
        report = MedicalReport.objects.get(pk=response.data["id"])
        lab = report.lab_results.get()
        self.assertEqual((lab.name, lab.value, lab.reference_low, lab.reference_high), ("Fasting glucose", 104, 70, 99))
        self.assertEqual(report.adherence_logs.count(), 7)
        self.assertEqual(report.extraction["blood_pressure"]["systolic"], 128)
        with transaction.atomic():
            extract_report_observations(report, io.BytesIO(self.pdf()))
        self.assertEqual(LabResult.objects.filter(report=report).count(), 1)
        self.assertEqual(MedicationAdherenceLog.objects.filter(report=report).count(), 7)

    def test_score_uses_unrounded_doses_and_report_measurement_date(self):
        self.assertEqual(self.upload().status_code, 201)
        data = dashboard_data(self.patient, self.owner)
        # Independent arithmetic: .30*85 + .20*70 + .30*70 + .20*75 = 75.5 -> 76.
        self.assertEqual(data["health_score"]["value"], 76)
        self.assertEqual([row["score"] for row in data["health_score"]["components"]], [85, 70, 70, 75])
        self.assertEqual(data["adherence"]["taken_doses"], 21)
        self.assertEqual(data["adherence"]["scheduled_doses"], 28)
        self.assertIsNone(data["risk_level"])
        self.assertIn("not clinically validated", data["health_score"]["disclaimer"])
        self.assertEqual(data["latest"]["blood_pressure"]["recorded_at"], self.measured.isoformat())
        self.assertEqual(data["latest"]["blood_sugar"]["value"], 104)
        self.assertEqual(data["lab_summary"], {"abnormal": 1, "total": 1})

    def test_low_measurements_do_not_receive_maximum_points(self):
        lines = [line.replace("Systolic-mmHg: 128", "Systolic-mmHg: 80").replace("Diastolic-mmHg: 82", "Diastolic-mmHg: 50").replace("Fasting-Glucose-mg-dL: 104", "Fasting-Glucose-mg-dL: 60") for line in self.lines()]
        self.assertEqual(self.upload(lines=lines).status_code, 201)
        self.assertEqual(dashboard_data(self.patient, self.owner)["health_score"]["value"], 44)

    def test_demo_score_rounds_half_up_consistently_with_the_popup(self):
        lines = [line.replace("|4|3", "|10|7") for line in self.lines()]
        self.assertEqual(self.upload(lines=lines).status_code, 201)
        # 25.5 + 14 + 21 + 14 = 74.5, displayed as 75 rather than bankers' 74.
        self.assertEqual(dashboard_data(self.patient, self.owner)["health_score"]["value"], 75)

    def test_missing_dose_coverage_or_stale_report_withholds_score(self):
        self.assertEqual(self.upload().status_code, 201)
        MedicationAdherenceLog.objects.filter(patient=self.patient).delete()
        self.assertIsNone(dashboard_data(self.patient, self.owner)["health_score"])
        report = MedicalReport.objects.get(patient=self.patient)
        report.extraction["measured_at"] = (timezone.now() - timedelta(days=46)).isoformat()
        report.save(update_fields=["extraction"])
        self.assertIn("45 days", dashboard_data(self.patient, self.owner)["health_score_reason"])

    def test_malformed_supported_reports_rollback_rows_and_files(self):
        mutations = [
            lambda rows: [line.replace(self.owner.account_id, self.other.account_id) for line in rows],
            lambda rows: [line.replace(self.doctor.account_id, self.doctor2.account_id) for line in rows],
            lambda rows: rows[:-1] + ["Systolic-mmHg: 128", rows[-1]],
            lambda rows: rows[:-1] + [rows[-2], rows[-1]],
            lambda rows: [line.replace("|4|3", "|4|5") for line in rows],
            lambda rows: [line.replace("Systolic-mmHg: 128", "Systolic-mmHg: NaN") for line in rows],
            lambda rows: [line.replace("Systolic-mmHg: 128", "Systolic-mmHg: 70") for line in rows],
            lambda rows: [f"Measured-At: {(timezone.now()+timedelta(days=1)).isoformat()}" if line.startswith("Measured-At:") else line for line in rows],
            lambda rows: [f"Measured-At: {self.measured.replace(tzinfo=None).isoformat()}" if line.startswith("Measured-At:") else line for line in rows],
            lambda rows: [f"Adherence-Period-Start: {self.today-timedelta(days=32)}" if line.startswith("Adherence-Period-Start:") else line for line in rows],
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                response = self.upload(lines=mutation(self.lines()))
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(MedicalReport.objects.exists())
                self.assertFalse(LabResult.objects.exists())
                self.assertFalse(MedicationAdherenceLog.objects.exists())
                self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_unsupported_patient_and_disabled_extraction_keep_files_without_guessed_values(self):
        self.assertEqual(self.upload(lines=["Unstructured clinical report"]).status_code, 201)
        self.assertEqual(self.upload(user=self.owner).status_code, 201)
        with override_settings(SYNTHETIC_REPORT_EXTRACTION_ALLOWED=False):
            self.assertEqual(self.upload().status_code, 201)
        self.assertEqual(MedicalReport.objects.count(), 3)
        self.assertFalse(LabResult.objects.exists())
        self.assertFalse(MedicationAdherenceLog.objects.exists())

    def test_manual_dose_correction_clears_pdf_provenance(self):
        self.assertEqual(self.upload().status_code, 201)
        response = self.as_user(self.owner).put("/api/v1/patients/me/adherence/", {
            "date": self.today.isoformat(), "scheduled_doses": 4, "taken_doses": 2,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(MedicationAdherenceLog.objects.get(patient=self.patient, date=self.today).report_id)

    def test_view_download_and_cross_patient_authorization(self):
        report_id = self.upload().data["id"]
        for suffix, disposition in [("view", "inline"), ("download", "attachment")]:
            response = self.as_user(self.owner).get(f"/api/v1/reports/{report_id}/{suffix}/")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response["Content-Disposition"].startswith(disposition))
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
            # Django's test streaming iterator already closes the response and
            # preserves the test transaction; a second close fires it again.
            self.assertTrue(response.closed)
            for denied in [self.other, self.admin, self.pharmacist]:
                response = self.as_user(denied).get(f"/api/v1/reports/{report_id}/{suffix}/")
                self.assertIn(response.status_code, (403, 404))
        self.assertEqual(AuditEvent.objects.filter(event="report.view", outcome="success").count(), 1)
        self.assertEqual(AuditEvent.objects.filter(event="report.download", outcome="success").count(), 1)
        self.assertEqual(dashboard_data(self.patient, self.owner)["counts"]["report_downloads"], 1)

    def test_identical_linked_consultation_measurement_is_not_counted_twice(self):
        self.record.vitals = {"systolic": 128, "diastolic": 82, "glucose_mg_dl": 104}
        self.record.save(update_fields=["vitals"])
        MedicalRecord.objects.filter(pk=self.record.pk).update(created_at=self.measured)
        self.assertEqual(self.upload().status_code, 201)
        data = dashboard_data(self.patient, self.owner)
        self.assertEqual(len(data["trends"]["blood_pressure"]), 1)
        self.assertEqual(len(data["trends"]["blood_sugar"]), 1)
        self.assertEqual(data["trends"]["blood_pressure"][0]["source"], "Monthly PDF report")

    def test_visit_and_prescription_query_counts_do_not_grow_with_history(self):
        ClinicalEntry.objects.create(patient=self.patient, author=self.doctor, kind="allergy", name="Fixture allergy", source="clinician_recorded")
        routes = ["/api/v1/patients/me/visits/", "/api/v1/patients/me/prescriptions/"]
        baseline = {}
        for route in routes:
            with CaptureQueriesContext(connection) as queries:
                response = self.as_user(self.owner).get(route)
                self.assertEqual(response.status_code, 200)
            baseline[route] = len(queries)
        for i in range(24):
            record = MedicalRecord.objects.create(patient=self.patient, doctor=self.doctor2, complaint=f"Follow-up {i}")
            rx = Prescription.objects.create(patient=self.patient, doctor=self.doctor2, application=self.apps[self.doctor2.pk], record=record, valid_until=timezone.now()+timedelta(days=30))
            PrescriptionItem.objects.create(prescription=rx, medicine="Fixture medicine", dosage="Fixture direction", quantity=30, unit="tablet")
        for route in routes:
            with CaptureQueriesContext(connection) as queries:
                response = self.as_user(self.owner).get(route)
                self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data["results"]), 25)
            self.assertLessEqual(len(queries), baseline[route] + 1, f"Queries grew with clinical rows: {route}")
            rx = response.data["results"][0]
            if "visits" in route:
                rx = rx["prescriptions"][0]
            self.assertEqual(rx["items"][0]["remaining"], "30.000")
            self.assertEqual(rx["allergies"][0]["name"], "Fixture allergy")
