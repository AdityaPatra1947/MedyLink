from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from .health_tracking import health_metrics, regional_alerts
from .models import AuditEvent, MedicalReport, MedicationAdherenceLog, Patient
from .tests import ClinicFixtures


def score_policy():
    return {
        "method": "Synthetic test calculation",
        "version": "test-v1",
        "label": "Test metric",
        "components": [
            {
                "key": "systolic",
                "label": "Test input A",
                "weight": 1,
                "max_age_days": 7,
                "rules": [
                    {"upper_bound": 120, "score": 80},
                    {"upper_bound": None, "score": 40},
                ],
            },
            {
                "key": "adherence",
                "label": "Test input B",
                "weight": 3,
                "max_age_days": 7,
                "rules": [
                    {"upper_bound": 50, "score": 20},
                    {"upper_bound": None, "score": 100},
                ],
            },
        ],
        "risk_bands": [
            {"min_score": 0, "label": "Test band A"},
            {"min_score": 90, "label": "Test band B"},
        ],
    }


class HealthTrackingTests(ClinicFixtures, TestCase):
    def setUp(self):
        self.setup_domain()
        self.today = timezone.localdate()
        self.other_patient = Patient.objects.create(user=self.other)

    def adherence(self, **overrides):
        data = {
            "date": self.today.isoformat(),
            "scheduled_doses": 3,
            "taken_doses": 2,
            **overrides,
        }
        return self.as_user(self.owner).put(
            "/api/v1/patients/me/adherence/", data, format="json"
        )

    def lab(self, user=None, patient_id=None, **overrides):
        data = {
            "name": "Example analyte",
            "value": "12.5",
            "unit": "example-unit",
            "measured_at": timezone.now().isoformat(),
            **overrides,
        }
        path = (
            f"/api/v1/patients/{patient_id}/labs/"
            if patient_id
            else "/api/v1/patients/me/labs/"
        )
        return self.as_user(user or self.owner).post(path, data, format="json")

    def test_empty_tracking_is_unknown(self):
        response = self.as_user(self.owner).get("/api/v1/patients/me/adherence/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"results": [], "summary": None})
        response = self.as_user(self.owner).get("/api/v1/patients/me/labs/")
        self.assertEqual(response.data["summary"], {"abnormal": None, "total": None})
        result = health_metrics(self.patient, {}, 0)
        self.assertIsNone(result["health_score"])
        self.assertIsNone(result["risk_level"])
        self.assertEqual(result["regional_alerts"], {"available": False, "items": []})

    def test_adherence_weighted_window_upsert_and_audit(self):
        self.assertEqual(self.adherence().status_code, 200)
        self.assertEqual(
            self.adherence(scheduled_doses=4, taken_doses=1).status_code, 200
        )
        self.adherence(
            date=(self.today - timedelta(days=1)).isoformat(),
            scheduled_doses=6,
            taken_doses=6,
        )
        MedicationAdherenceLog.objects.create(
            patient=self.patient,
            date=self.today - timedelta(days=30),
            scheduled_doses=100,
            taken_doses=0,
        )
        result = self.as_user(self.owner).get("/api/v1/patients/me/adherence/").data
        self.assertEqual(
            {key: result["summary"][key] for key in ("percentage", "scheduled_doses", "taken_doses", "days_logged", "period_days")},
            {
                "percentage": 70.0,
                "scheduled_doses": 10,
                "taken_doses": 7,
                "days_logged": 2,
                "period_days": 30,
            },
        )
        self.assertEqual(result["summary"]["missing_days"], 28)
        self.assertEqual(result["summary"]["report_ids"], [])
        self.assertEqual(result["summary"]["self_reported_days"], 2)
        self.assertEqual(
            MedicationAdherenceLog.objects.filter(
                patient=self.patient, date=self.today
            ).count(),
            1,
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                patient=self.patient, event="adherence.update"
            ).exists()
        )

    def test_adherence_strict_integer_bounds_and_dates(self):
        for data in [
            {"taken_doses": True},
            {"taken_doses": 1.5},
            {"taken_doses": 1.0},
            {"taken_doses": "1"},
            {"scheduled_doses": 0},
            {"taken_doses": -1},
            {"taken_doses": 4},
            {"date": (self.today + timedelta(days=1)).isoformat()},
            {"date": (self.today - timedelta(days=30)).isoformat()},
        ]:
            with self.subTest(data=data):
                self.assertEqual(self.adherence(**data).status_code, 400)
        self.assertFalse(MedicationAdherenceLog.objects.exists())

    def test_adherence_is_patient_only_and_isolated(self):
        self.adherence()
        self.assertIsNone(
            self.as_user(self.other)
            .get("/api/v1/patients/me/adherence/")
            .data["summary"]
        )
        for user in [self.doctor, self.pharmacist, self.admin]:
            self.assertEqual(
                self.as_user(user).get("/api/v1/patients/me/adherence/").status_code,
                403,
            )
        self.assertEqual(
            self.adherence(patient_id=str(self.other_patient.id)).status_code, 400
        )

    def test_lab_range_and_unknown_flags(self):
        unknown = self.lab()
        self.assertEqual(unknown.status_code, 201)
        self.assertEqual(unknown.data["flag"], "unknown")
        self.assertEqual(
            self.as_user(self.owner).get("/api/v1/patients/me/labs/").data["summary"],
            {"abnormal": None, "total": 1},
        )
        for value, low, high, flag in [
            (2, 3, 10, "low"),
            (12, 3, 10, "high"),
            (3, 3, 10, "normal"),
            (10, 3, 10, "normal"),
            (2, None, 10, "normal"),
        ]:
            with self.subTest(value=value):
                response = self.lab(value=value, reference_low=low, reference_high=high)
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.data["flag"], flag)
        self.assertEqual(self.lab(reference_low=10, reference_high=3).status_code, 400)
        self.assertEqual(self.lab(value="NaN").status_code, 400)
        self.assertEqual(
            self.lab(
                measured_at=(timezone.now() + timedelta(days=1)).isoformat()
            ).status_code,
            400,
        )

    def test_lab_summary_uses_latest_per_name_and_unit(self):
        # Clock resolution can make consecutive requests share a timestamp;
        # explicit observation dates make the intended chronology deterministic.
        measured = timezone.now() - timedelta(days=1)
        self.lab(name="Example", value=20, reference_high=10, measured_at=(measured - timedelta(days=1)).isoformat())
        self.lab(name="example", value=5, reference_high=10, measured_at=measured.isoformat())
        self.lab(name="Different", value=20, reference_high=10)
        self.lab(name="Unclassified", value=3)
        summary = (
            self.as_user(self.owner).get("/api/v1/patients/me/labs/").data["summary"]
        )
        self.assertEqual(summary, {"abnormal": 1, "total": 3})
        self.lab(name="Example", unit="M", value=2, reference_high=1)
        self.lab(name="example", unit="m", value=2, reference_high=1)
        self.assertEqual(
            self.as_user(self.owner).get("/api/v1/patients/me/labs/").data["summary"],
            {"abnormal": 3, "total": 5},
        )

    def test_lab_permissions_patient_isolation_and_author_attribution(self):
        response = self.lab(user=self.doctor, patient_id=self.patient.id)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["source"], "doctor")
        self.assertEqual(response.data["recorded_by_name"], self.doctor.name)
        self.assertEqual(
            self.as_user(self.other).get("/api/v1/patients/me/labs/").data["results"],
            [],
        )
        path = f"/api/v1/patients/{self.patient.id}/labs/"
        for user in [self.pharmacist, self.admin, self.other]:
            self.assertEqual(self.as_user(user).get(path).status_code, 403)
            self.assertEqual(
                self.lab(user=user, patient_id=self.patient.id).status_code, 403
            )
        self.apps[self.doctor.id].status = "suspended"
        self.apps[self.doctor.id].save(update_fields=["status"])
        self.assertEqual(
            self.lab(user=self.doctor, patient_id=self.patient.id).status_code, 403
        )

    def test_lab_report_must_belong_to_patient_and_append_only(self):
        report = MedicalReport.objects.create(
            patient=self.other_patient,
            uploaded_by=self.other,
            name="private.pdf",
            storage_name="private-test-file",
            content_type="application/pdf",
            size_bytes=20,
        )
        self.assertEqual(self.lab(report_id=str(report.id)).status_code, 404)
        response = self.lab()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.as_user(self.owner)
            .put("/api/v1/patients/me/labs/", {}, format="json")
            .status_code,
            405,
        )
        self.assertEqual(
            self.as_user(self.owner)
            .patch("/api/v1/patients/me/labs/", {}, format="json")
            .status_code,
            405,
        )
        self.assertEqual(self.lab(recorded_by=str(self.doctor.id)).status_code, 400)

    def test_unverified_and_inactive_accounts_cannot_record(self):
        self.owner.email_verified_at = None
        self.owner.save(update_fields=["email_verified_at"])
        self.assertEqual(self.adherence().status_code, 403)
        self.assertEqual(self.lab().status_code, 403)

    @override_settings(HEALTH_SCORE_POLICY=score_policy())
    def test_configured_score_is_weighted_and_reports_method(self):
        self.adherence(scheduled_doses=10, taken_doses=9)
        trends = {
            "blood_pressure": [
                {"systolic": 110, "recorded_at": timezone.now().isoformat()}
            ]
        }
        data = health_metrics(self.patient, trends, 0)
        self.assertEqual(data["health_score"]["value"], 95)
        self.assertEqual(data["risk_level"], "Test band B")
        self.assertEqual(
            data["health_score"]["method"], "Synthetic test calculation (test-v1)"
        )
        self.assertEqual(len(data["health_score"]["components"]), 2)

    @override_settings(HEALTH_SCORE_POLICY=score_policy())
    def test_score_requires_every_input_and_freshness(self):
        self.adherence(scheduled_doses=10, taken_doses=9)
        self.assertIsNone(health_metrics(self.patient, {}, 0)["health_score"])
        trends = {
            "blood_pressure": [
                {
                    "systolic": 110,
                    "recorded_at": (timezone.now() - timedelta(days=8)).isoformat(),
                }
            ]
        }
        self.assertIsNone(health_metrics(self.patient, trends, 0)["health_score"])
        self.assertIsNone(health_metrics(self.patient, trends, 0)["risk_level"])

    def test_invalid_score_policy_fails_closed(self):
        policies = [False, {}, {**score_policy(), "components": [{"key": []}]}]
        unordered = deepcopy(score_policy())
        unordered["components"][0]["rules"] = [{"upper_bound": 120, "score": 80}]
        policies.append(unordered)
        missing_band = deepcopy(score_policy())
        missing_band["risk_bands"] = [{"min_score": 80, "label": "A"}]
        policies.append(missing_band)
        for policy in policies:
            with (
                self.subTest(policy=policy),
                override_settings(HEALTH_SCORE_POLICY=policy),
            ):
                self.assertIsNone(health_metrics(self.patient, {}, 0)["health_score"])

    def test_alert_provider_validates_urls_and_hides_failures(self):
        alert = {
            "id": "alert-1",
            "title": "Source announcement",
            "description": "Source supplied text",
            "region": "Test region",
            "source_url": "https://example.org/notice",
            "published_at": timezone.now().isoformat(),
        }
        with (
            override_settings(HEALTH_ALERTS_PROVIDER="operator.alerts"),
            patch("clinic.health_tracking.import_string") as imported,
        ):
            imported.return_value.return_value = {"available": True, "items": [alert]}
            result = regional_alerts(self.patient)
            self.assertTrue(result["available"])
            self.assertEqual(result["items"][0]["id"], "alert-1")
            imported.return_value.return_value = {
                "available": True,
                "items": [{**alert, "source_url": "javascript:alert(1)"}],
            }
            self.assertEqual(
                regional_alerts(self.patient), {"available": False, "items": []}
            )
            imported.return_value.side_effect = RuntimeError(
                "PRIVATE data must not appear in logs"
            )
            with self.assertLogs("clinic.health_tracking", level="WARNING") as logs:
                self.assertFalse(regional_alerts(self.patient)["available"])
            self.assertNotIn("PRIVATE", " ".join(logs.output))
