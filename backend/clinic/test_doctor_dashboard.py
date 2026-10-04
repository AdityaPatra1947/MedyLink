from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from .models import AuditEvent, ClinicalEntry, DoctorPatient, MedicalRecord, Patient
from .tests import ClinicFixtures


class DoctorDashboardTests(ClinicFixtures, TestCase):
    def setUp(self):
        self.setup_domain()
        self.list_path = "/api/v1/doctor/patients/"
        self.add_path = f"{self.list_path}{self.patient.id}/"
        self.summary_path = f"/api/v1/patients/{self.patient.id}/clinical-summary/"

    def test_lookup_by_qr_or_id_does_not_save_until_explicit_add(self):
        for identifier in [self.patient.card_locator, self.owner.account_id.lower()]:
            response = self.as_user(self.doctor2).post(
                "/api/v1/provider/patients/lookup/",
                {"identifier": identifier},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["patient_id"], str(self.patient.id))
            self.assertFalse(self.client.get(self.summary_path).data["is_my_patient"])
            self.assertEqual(self.client.get(self.list_path).data["results"], [])
        first = self.client.post(self.add_path, {}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertTrue(first.data["created"])
        again = self.client.post(self.add_path, {}, format="json")
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.data["created"])
        self.assertEqual(DoctorPatient.objects.count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(event="doctor.patient.add").count(), 1
        )
        self.assertTrue(self.client.get(self.summary_path).data["is_my_patient"])
        self.assertEqual(
            [row["id"] for row in self.client.get(self.list_path).data["results"]],
            [str(self.patient.id)],
        )
        self.assertEqual(
            self.as_user(self.doctor).get(self.list_path).data["results"], []
        )
        self.assertFalse(self.client.get(self.summary_path).data["is_my_patient"])

    def test_saved_patients_never_bypass_approval_or_account_status(self):
        self.assertEqual(self.as_user(self.doctor).post(self.add_path).status_code, 201)
        application = self.apps[self.doctor.id]
        for status in ["pending", "rejected", "suspended"]:
            application.status = status
            application.save(update_fields=["status"])
            self.assertEqual(self.client.get(self.list_path).status_code, 403)
            self.assertEqual(self.client.post(self.add_path).status_code, 403)
            self.assertEqual(self.client.get(self.summary_path).status_code, 403)
        application.status = "approved"
        application.valid_until = timezone.now() - timedelta(seconds=1)
        application.save(update_fields=["status", "valid_until"])
        self.assertEqual(self.client.get(self.list_path).status_code, 403)
        application.valid_until = timezone.now() + timedelta(days=2)
        application.save(update_fields=["valid_until"])
        for changes in [{"email_verified_at": None}, {"is_active": False}]:
            get_user_model().objects.filter(pk=self.doctor.pk).update(**changes)
            self.assertEqual(self.client.get(self.list_path).status_code, 403)
            self.assertEqual(self.client.post(self.add_path).status_code, 403)
            get_user_model().objects.filter(pk=self.doctor.pk).update(
                email_verified_at=timezone.now(), is_active=True
            )
        self.assertEqual(DoctorPatient.objects.count(), 1)
        self.assertEqual(self.client.get(self.list_path).status_code, 200)

    def test_patient_saving_is_doctor_only_and_inactive_patients_are_excluded(self):
        for user in [self.owner, self.other, self.pharmacist, self.admin]:
            self.assertEqual(self.as_user(user).get(self.list_path).status_code, 403)
            self.assertEqual(self.client.post(self.add_path).status_code, 403)
        self.assertEqual(self.as_user(self.doctor).post(self.add_path).status_code, 201)
        get_user_model().objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assertEqual(self.client.post(self.add_path).status_code, 404)
        self.assertEqual(self.client.get(self.list_path).data["results"], [])

    def test_saved_patients_pagination_is_complete_and_stable(self):
        User = get_user_model()
        for index in range(51):
            user = User.objects.create_user(
                f"saved-patient-{index}@example.com",
                "password",
                name=f"Patient {index}",
                role="patient",
                email_verified_at=timezone.now(),
            )
            patient = Patient.objects.create(user=user)
            DoctorPatient.objects.create(doctor=self.doctor, patient=patient)
        first = self.as_user(self.doctor).get(self.list_path)
        second = self.client.get(self.list_path + "?page=2")
        self.assertEqual(len(first.data["results"]), 50)
        self.assertEqual(first.data["next"], 2)
        self.assertEqual(len(second.data["results"]), 1)
        self.assertIsNone(second.data["next"])
        identifiers = [
            row["id"] for row in first.data["results"] + second.data["results"]
        ]
        self.assertEqual(len(set(identifiers)), 51)

    def test_other_doctor_history_is_readable_but_cannot_be_changed(self):
        entry = ClinicalEntry.objects.create(
            patient=self.patient,
            author=self.doctor,
            kind="condition",
            name="Prior condition",
            source="clinician_recorded",
        )
        response = self.as_user(self.doctor2).get(self.summary_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["records"][0]["id"], str(self.record.id))
        self.assertEqual(response.data["prescriptions"][0]["id"], str(self.rx.id))
        self.assertEqual(
            response.data["conditions"][0]["author_id"], str(self.doctor.id)
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/records/{self.record.id}/corrections/",
                {"complaint": "Overwritten", "correction_reason": "Test"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/prescriptions/{self.rx.id}/cancel/",
                {"reason": "Test"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/patients/{self.patient.id}/conditions/{entry.id}/resolve/",
                {"reason": "Test"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/v1/patients/{self.patient.id}/records/",
                {"complaint": "Overwritten"},
                format="json",
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/records/{self.record.id}/corrections/",
            ).status_code,
            405,
        )
        created = self.client.post(
            f"/api/v1/patients/{self.patient.id}/records/",
            {"complaint": "New consultation", "notes": "New doctor notes"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["doctor_id"], str(self.doctor2.id))
        self.assertFalse(DoctorPatient.objects.exists())
        self.record.refresh_from_db()
        self.rx.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(self.record.complaint, "PRIVATE COMPLAINT")
        self.assertIsNone(self.rx.cancelled_at)
        self.assertIsNone(entry.resolved_at)

    def test_doctor_profile_updates_contact_without_changing_reviewed_credentials(self):
        path = "/api/v1/doctor/profile/"
        application = self.apps[self.doctor.id]
        application.status = "pending"
        application.save(update_fields=["status"])
        response = self.as_user(self.doctor).get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["account_id"], self.doctor.account_id)
        self.assertEqual(response.data["application"]["status"], "pending")
        old_application = dict(application.__dict__)
        response = self.client.patch(
            path, {"name": "  Updated Doctor  ", "phone": "+91 12345"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["name"], "Updated Doctor")
        self.assertEqual(response.data["user"]["phone"], "+91 12345")
        application.refresh_from_db()
        self.assertEqual(
            application.registration_number, old_application["registration_number"]
        )
        self.assertEqual(application.contact_phone, old_application["contact_phone"])
        self.assertEqual(application.status, "pending")
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.doctor, event="doctor.profile.update"
            ).exists()
        )
        self.assertEqual(
            self.client.patch(path, {"phone": ""}, format="json").status_code, 200
        )

    def test_doctor_profile_rejects_immutable_fields_invalid_input_and_other_roles(
        self,
    ):
        path = "/api/v1/doctor/profile/"
        self.as_user(self.doctor)
        for data in [
            {"email": "replacement@example.com"},
            {"account_id": "D-AAAAAA"},
            {"role": "admin"},
            {"is_staff": True},
            {"registration_number": "CHANGED"},
            {"name": " "},
            {"name": "X" * 151},
            {"phone": "X" * 31},
            {},
        ]:
            self.assertEqual(
                self.client.patch(path, data, format="json").status_code, 400, data
            )
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.name, "Doctor A")
        self.assertEqual(self.doctor.role, "doctor")
        for user in [self.owner, self.pharmacist, self.admin]:
            self.assertEqual(self.as_user(user).get(path).status_code, 403)
            self.assertEqual(
                self.client.patch(
                    path, {"name": "New name"}, format="json"
                ).status_code,
                403,
            )
        for field, value in [("email_verified_at", None), ("is_active", False)]:
            original = getattr(self.doctor, field)
            setattr(self.doctor, field, value)
            self.doctor.save(update_fields=[field])
            self.assertEqual(self.as_user(self.doctor).get(path).status_code, 403)
            self.assertEqual(
                self.client.patch(
                    path, {"name": "New name"}, format="json"
                ).status_code,
                403,
            )
            setattr(self.doctor, field, original)
            self.doctor.save(update_fields=[field])


class DoctorPatientsMigrationTests(ClinicFixtures, TransactionTestCase):
    def restore_latest_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self, migration):
        targets = [("clinic", migration)]
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_historical_consultations_and_prescriptions_are_saved_once(self):
        latest = "0004_doctor_patient"
        self.addCleanup(self.restore_latest_schema)
        self.migrate("0003_patient_photo_content_type_and_more")
        self.setup_domain()
        second = Patient.objects.create(user=self.other)
        MedicalRecord.objects.create(
            patient=second, doctor=self.doctor2, complaint="Prior visit"
        )
        self.rx.patient = second
        self.rx.record = None
        self.rx.save(update_fields=["patient", "record"])
        apps = self.migrate(latest)
        expected = {
            (self.doctor.id, self.patient.id),
            (self.doctor.id, second.id),
            (self.doctor2.id, second.id),
        }
        actual = set(DoctorPatient.objects.values_list("doctor_id", "patient_id"))
        self.assertEqual(actual, expected)
        migration = import_module("clinic.migrations.0004_doctor_patient")
        migration.preserve_existing_patients(
            apps, SimpleNamespace(connection=connection)
        )
        self.assertEqual(
            set(DoctorPatient.objects.values_list("doctor_id", "patient_id")), expected
        )
        self.assertEqual(DoctorPatient.objects.count(), 3)
