from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    AccessGrant,
    AccessRequest,
    ClinicalEntry,
    DispenseEvent,
    MedicalRecord,
    Patient,
    Prescription,
    PrescriptionItem,
    ProviderApplication,
)


class ClinicFixtures:
    def setup_domain(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            "owner@example.com",
            "password",
            name="Patient One",
            role="patient",
            email_verified_at=timezone.now(),
        )
        self.other = User.objects.create_user(
            "other@example.com",
            "password",
            name="Patient Two",
            role="patient",
            email_verified_at=timezone.now(),
        )
        self.doctor = User.objects.create_user(
            "doctor@example.com",
            "password",
            name="Doctor A",
            role="doctor",
            email_verified_at=timezone.now(),
        )
        self.doctor2 = User.objects.create_user(
            "doctor2@example.com",
            "password",
            name="Doctor B",
            role="doctor",
            email_verified_at=timezone.now(),
        )
        self.pharmacist = User.objects.create_user(
            "pharmacy@example.com",
            "password",
            name="Pharmacist A",
            role="pharmacist",
            email_verified_at=timezone.now(),
        )
        self.pharmacist2 = User.objects.create_user(
            "pharmacy2@example.com",
            "password",
            name="Pharmacist B",
            role="pharmacist",
            email_verified_at=timezone.now(),
        )
        self.admin = User.objects.create_user(
            "admin@example.com",
            "password",
            name="Reviewer",
            role="admin",
            email_verified_at=timezone.now(),
        )
        self.patient = Patient.objects.create(
            user=self.owner, date_of_birth=date(1990, 1, 1)
        )
        self.apps = {}
        for user in [self.doctor, self.doctor2, self.pharmacist, self.pharmacist2]:
            self.apps[user.pk] = ProviderApplication.objects.create(
                provider=user,
                version=1,
                status="approved",
                registration_number=str(user.id),
                registering_body="COUNCIL",
                practice_address="Clinic address",
                shop_name="Shop " + user.name if user.role == "pharmacist" else "",
                shop_license=str(user.id) if user.role == "pharmacist" else "",
                shop_license_expires=timezone.localdate() + timedelta(days=365),
                valid_until=timezone.now() + timedelta(days=90),
            )
        self.record = MedicalRecord.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            complaint="PRIVATE COMPLAINT",
            diagnosis="PRIVATE DIAGNOSIS",
            notes="SECRET ENCOUNTER NOTES",
        )
        self.rx = Prescription.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            application=self.apps[self.doctor.id],
            record=self.record,
            valid_until=timezone.now() + timedelta(days=3),
            notes="Take as instructed",
        )
        self.item = PrescriptionItem.objects.create(
            prescription=self.rx,
            medicine="Medicine",
            dosage="Prescriber directions",
            quantity=Decimal("10"),
            unit="tablet",
        )
        self.grants = {}
        for user in [self.doctor, self.doctor2, self.pharmacist, self.pharmacist2]:
            scope = "clinical" if user.role == "doctor" else "dispensing"
            req = AccessRequest.objects.create(
                patient=self.patient,
                provider=user,
                application=self.apps[user.pk],
                scope=scope,
                purpose="Care",
                status="approved",
            )
            self.grants[user.pk] = AccessGrant.objects.create(
                request=req,
                patient=self.patient,
                provider=user,
                application=self.apps[user.pk],
                scope=scope,
                prescription=self.rx if scope == "dispensing" else None,
                expires_at=timezone.now() + timedelta(hours=1),
            )
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def dispense(self, user, qty="6", key="unique-key", **kwargs):
        return self.as_user(user).post(
            f"/api/v1/prescriptions/{self.rx.id}/dispense/",
            {
                "items": [
                    {
                        "prescription_item_id": str(self.item.id),
                        "quantity": qty,
                        "unit": "tablet",
                    }
                ]
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            **kwargs,
        )


class ClinicTests(ClinicFixtures, TestCase):
    def setUp(self):
        self.setup_domain()

    def test_clinical_permission_matrix(self):
        path = f"/api/v1/patients/{self.patient.pk}/clinical-summary/"
        for user, code in [
            (self.owner, 200),
            (self.doctor, 200),
            (self.doctor2, 200),
            (self.pharmacist, 403),
            (self.admin, 403),
            (self.other, 403),
        ]:
            self.assertEqual(self.as_user(user).get(path).status_code, code, user.role)
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(path).status_code, [401, 403])

    def test_prescription_pharmacy_boundary_and_pdf(self):
        ClinicalEntry.objects.create(
            patient=self.patient,
            author=self.owner,
            kind="allergy",
            name="Peanut",
            notes="Patient reported",
            source="patient_reported",
        )
        response = self.as_user(self.pharmacist).get(
            f"/api/v1/prescriptions/{self.rx.pk}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Peanut", str(response.data))
        for secret in [
            "PRIVATE DIAGNOSIS",
            "SECRET ENCOUNTER NOTES",
            "PRIVATE COMPLAINT",
            "record_id",
            "phone",
            "address",
        ]:
            self.assertNotIn(secret, str(response.data))
        pdf = self.client.get(f"/api/v1/prescriptions/{self.rx.pk}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertIn("no-store", pdf["Cache-Control"])
        self.assertTrue(b"".join(pdf.streaming_content).startswith(b"%PDF"))
        self.grants[
            self.pharmacist.id
        ].delete()  # test fixture removal; no application delete endpoint
        self.assertEqual(
            self.client.get(f"/api/v1/prescriptions/{self.rx.pk}/pdf/").status_code, 200
        )

    def test_quantity_is_shared_idempotent_and_payload_bound(self):
        first = self.dispense(self.pharmacist)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(self.dispense(self.pharmacist).status_code, 200)
        self.assertEqual(self.dispense(self.pharmacist, qty="5").status_code, 409)
        self.assertEqual(
            self.dispense(self.pharmacist2, qty="5", key="shop-two").status_code, 409
        )
        self.assertEqual(
            self.dispense(self.pharmacist2, qty="4", key="shop-two").status_code, 201
        )
        self.assertEqual(DispenseEvent.objects.count(), 2)
        response = self.as_user(self.owner).get(f"/api/v1/prescriptions/{self.rx.pk}/")
        self.assertEqual(response.data["status"], "fulfilled")
        self.assertEqual(Decimal(response.data["items"][0]["remaining"]), 0)

    def test_replay_ignores_legacy_grant_but_rechecks_provider(self):
        self.assertEqual(self.dispense(self.pharmacist).status_code, 201)
        grant = self.grants[self.pharmacist.id]
        grant.revoked_at = timezone.now()
        grant.save()
        self.assertEqual(self.dispense(self.pharmacist).status_code, 200)
        grant.revoked_at = None
        grant.save()
        app = self.apps[self.pharmacist.pk]
        app.status = "suspended"
        app.save()
        self.assertEqual(self.dispense(self.pharmacist).status_code, 403)

    def test_dispense_validates_entire_batch_and_units(self):
        path = f"/api/v1/prescriptions/{self.rx.id}/dispense/"
        for qty in ["0", "-1", "0.0001", "NaN", "Infinity"]:
            self.assertEqual(self.dispense(self.pharmacist, qty=qty).status_code, 400)
        row = {
            "prescription_item_id": str(self.item.id),
            "quantity": "1",
            "unit": "tablet",
        }
        self.assertEqual(
            self.as_user(self.pharmacist)
            .post(
                path,
                {"items": [row, row]},
                format="json",
                HTTP_IDEMPOTENCY_KEY="duplicate",
            )
            .status_code,
            400,
        )
        row["unit"] = "ml"
        self.assertEqual(
            self.client.post(
                path, {"items": [row]}, format="json", HTTP_IDEMPOTENCY_KEY="wrong-unit"
            ).status_code,
            400,
        )
        self.assertEqual(DispenseEvent.objects.count(), 0)

    def test_records_are_attributed_and_only_author_can_correct(self):
        path = f"/api/v1/records/{self.record.id}/corrections/"
        data = {
            "complaint": "Updated complaint",
            "correction_reason": "Corrected transcription",
        }
        self.assertEqual(
            self.as_user(self.doctor2).post(path, data, format="json").status_code, 403
        )
        self.assertEqual(
            self.as_user(self.owner).post(path, data, format="json").status_code, 403
        )
        self.assertEqual(
            self.as_user(self.doctor).post(path, data, format="json").status_code, 201
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.complaint, "PRIVATE COMPLAINT")
        self.assertEqual(
            MedicalRecord.objects.get(correction_of=self.record).doctor, self.doctor
        )

    def test_legacy_grants_ignored_suspension_and_card_replacement(self):
        path = f"/api/v1/patients/{self.patient.id}/records/"
        grant = self.grants[self.doctor.id]
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save()
        self.assertEqual(self.as_user(self.doctor).get(path).status_code, 200)
        response = self.as_user(self.admin).post(
            f"/api/v1/admin/providers/{self.doctor2.id}/suspend/",
            {"reason": "Credential review"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.grants[self.doctor2.id].refresh_from_db()
        self.assertIsNotNone(self.grants[self.doctor2.id].revoked_at)
        old = self.patient.card_locator
        stable_id = self.patient.health_id
        self.assertEqual(
            self.as_user(self.owner)
            .post("/api/v1/patients/me/card/replace/", {}, format="json")
            .status_code,
            200,
        )
        self.patient.refresh_from_db()
        self.assertNotEqual(old, self.patient.card_locator)
        self.assertEqual(stable_id, self.patient.health_id)
        self.assertEqual(self.as_user(self.doctor).get(path).status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/v1/provider/patients/lookup/", {"identifier": old}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/provider/patients/lookup/",
                {"identifier": self.patient.card_locator},
                format="json",
            ).status_code,
            200,
        )

    def test_direct_lookup_restricts_roles_and_returns_only_identity(self):
        endpoint = "/api/v1/provider/patients/lookup/"
        for user in [self.doctor, self.pharmacist]:
            response = self.as_user(user).post(
                endpoint, {"identifier": self.patient.health_id}, format="json"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["patient_id"], str(self.patient.id))
            self.assertEqual(
                set(response.data["patient"]),
                {"id", "account_id", "name", "health_id", "date_of_birth", "photo_url"},
            )
            self.assertEqual(
                self.client.post(
                    endpoint, {"identifier": "AT-MISSING"}, format="json"
                ).status_code,
                404,
            )
        for user in [self.owner, self.other, self.admin]:
            self.assertEqual(
                self.as_user(user)
                .post(endpoint, {"identifier": self.patient.health_id}, format="json")
                .status_code,
                403,
            )
        self.apps[self.doctor.id].status = "suspended"
        self.apps[self.doctor.id].save()
        self.assertEqual(
            self.as_user(self.doctor)
            .post(endpoint, {"identifier": self.patient.health_id}, format="json")
            .status_code,
            403,
        )

    def test_compact_id_lookup_preserves_legacy_card_identifiers(self):
        endpoint = "/api/v1/provider/patients/lookup/"
        for identifier in [
            self.owner.account_id,
            self.owner.account_id.lower(),
            self.patient.health_id,
            self.patient.card_locator,
        ]:
            response = self.as_user(self.doctor).post(
                endpoint, {"identifier": identifier}, format="json"
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(
                response.data["patient"]["account_id"], self.owner.account_id
            )
            self.assertEqual(response.data["patient_id"], str(self.patient.id))
        profile = self.as_user(self.owner).get("/api/v1/patients/me/")
        card = self.client.get("/api/v1/patients/me/card/")
        self.assertEqual(profile.data["account_id"], self.owner.account_id)
        self.assertEqual(card.data["account_id"], self.owner.account_id)
        self.assertEqual(card.data["health_id"], self.patient.health_id)
        self.assertEqual(card.data["locator"], self.patient.card_locator)
        response = self.as_user(self.pharmacist).get(
            f"/api/v1/prescriptions/{self.rx.id}/"
        )
        self.assertEqual(response.data["patient"]["account_id"], self.owner.account_id)

    def test_access_routes_removed_and_doctor_list_requires_explicit_save(self):
        for path in [
            "access-requests/",
            "access-grants/",
            f"access-grants/{self.grants[self.doctor.id].id}/revoke/",
        ]:
            self.assertEqual(
                self.as_user(self.owner).get("/api/v1/" + path).status_code, 404
            )
        response = self.as_user(self.doctor).get("/api/v1/doctor/patients/")
        self.assertEqual(response.data["results"], [])
        saved = self.client.post(
            f"/api/v1/doctor/patients/{self.patient.id}/", {}, format="json"
        )
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(
            [
                p["id"]
                for p in self.client.get("/api/v1/doctor/patients/").data["results"]
            ],
            [str(self.patient.id)],
        )
        response = self.as_user(self.doctor2).get("/api/v1/doctor/patients/")
        self.assertEqual(response.data["results"], [])
        MedicalRecord.objects.create(
            patient=self.patient, doctor=self.doctor2, complaint="New visit"
        )
        self.assertEqual(
            self.client.get("/api/v1/doctor/patients/").data["results"], []
        )

    def test_pharmacy_lists_prescriptions_without_full_clinical_access(self):
        path = f"/api/v1/patients/{self.patient.id}/prescriptions/"
        response = self.as_user(self.pharmacist).get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["id"], str(self.rx.id))
        self.assertNotIn("record_id", response.data["results"][0])
        self.assertNotIn("SECRET ENCOUNTER", str(response.data))
        self.assertEqual(self.as_user(self.other).get(path).status_code, 403)
        self.assertEqual(self.as_user(self.admin).get(path).status_code, 403)
        self.apps[self.pharmacist.id].valid_until = timezone.now() - timedelta(
            seconds=1
        )
        self.apps[self.pharmacist.id].save()
        self.assertEqual(self.as_user(self.pharmacist).get(path).status_code, 403)

    def test_cancelled_and_expired_prescription_reject_dispense(self):
        self.rx.valid_until = timezone.now() - timedelta(days=1)
        self.rx.save()
        self.assertEqual(self.dispense(self.pharmacist).status_code, 409)
        self.rx.valid_until = timezone.now() + timedelta(days=1)
        self.rx.cancelled_at = timezone.now()
        self.rx.save()
        self.assertEqual(self.dispense(self.pharmacist).status_code, 409)

    def test_current_approval_allows_direct_access_and_pending_does_not(self):
        app = self.apps[self.doctor.pk]
        app.is_current = False
        app.save()
        ProviderApplication.objects.create(
            provider=self.doctor,
            version=2,
            registration_number=app.registration_number,
            registering_body=app.registering_body,
            practice_address="New clinic",
            status="approved",
            valid_until=timezone.now() + timedelta(days=30),
        )
        self.assertEqual(
            self.as_user(self.doctor)
            .get(f"/api/v1/patients/{self.patient.id}/records/")
            .status_code,
            200,
        )
        current = ProviderApplication.objects.get(provider=self.doctor, is_current=True)
        current.status = "pending"
        current.save()
        self.assertEqual(self.client.get("/api/v1/doctor/patients/").status_code, 403)

    def test_document_upload_rejects_disguised_contents(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile(
            "evidence.pdf", b"<script>alert(1)</script>", content_type="application/pdf"
        )
        response = self.as_user(self.doctor).post(
            "/api/v1/provider/application/documents/",
            {"file": uploaded},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)


@skipUnless(
    connection.vendor == "postgresql",
    "Requires TEST_DATABASE_URL pointing to PostgreSQL for row-lock guarantees.",
)
class PostgreSQLConcurrencyTests(ClinicFixtures, TransactionTestCase):
    def setUp(self):
        self.setup_domain()

    def run_parallel(self, operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            client = APIClient()
            barrier.wait(timeout=10)
            try:
                return operation(client)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            return list(executor.map(run, operations))

    def pharmacy_operation(self, user, key, quantity="6"):
        def operation(client):
            client.force_authenticate(user=user)
            response = client.post(
                f"/api/v1/prescriptions/{self.rx.id}/dispense/",
                {
                    "items": [
                        {
                            "prescription_item_id": str(self.item.id),
                            "quantity": quantity,
                            "unit": "tablet",
                        }
                    ]
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=key,
            )
            return response.status_code

        return operation

    def test_two_shops_cannot_overdispense(self):
        outcomes = self.run_parallel(
            [
                self.pharmacy_operation(self.pharmacist, "race-a"),
                self.pharmacy_operation(self.pharmacist2, "race-b"),
            ]
        )
        self.assertEqual(sorted(outcomes), [201, 409])
        self.assertEqual(
            sum(self.item.dispenses.values_list("quantity", flat=True)), Decimal("6")
        )

    def test_concurrent_same_key_writes_once(self):
        outcomes = self.run_parallel(
            [
                self.pharmacy_operation(self.pharmacist, "same"),
                self.pharmacy_operation(self.pharmacist, "same"),
            ]
        )
        self.assertEqual(sorted(outcomes), [200, 201])
        self.assertEqual(DispenseEvent.objects.count(), 1)

    def test_cancellation_serializes_with_dispensing(self):
        def cancel(client):
            client.force_authenticate(user=self.doctor)
            return client.post(
                f"/api/v1/prescriptions/{self.rx.id}/cancel/",
                {"reason": "Treatment changed"},
                format="json",
            ).status_code

        outcomes = self.run_parallel(
            [self.pharmacy_operation(self.pharmacist, "cancel-race"), cancel]
        )
        self.assertEqual(outcomes[1], 200)
        self.assertIn(outcomes[0], [201, 409])
        self.assertEqual(self.dispense(self.pharmacist, key="later").status_code, 409)

    def test_suspension_serializes_with_dispensing(self):
        def suspend(client):
            client.force_authenticate(user=self.admin)
            return client.post(
                f"/api/v1/admin/providers/{self.pharmacist.pk}/suspend/",
                {"reason": "Review required"},
                format="json",
            ).status_code

        outcomes = self.run_parallel(
            [self.pharmacy_operation(self.pharmacist, "suspend-race"), suspend]
        )
        self.assertEqual(outcomes[1], 200)
        self.assertIn(outcomes[0], [201, 403])
        self.assertEqual(self.dispense(self.pharmacist, key="later").status_code, 403)

    def test_concurrent_patient_add_creates_one_relationship(self):
        from .models import DoctorPatient

        def add(client):
            client.force_authenticate(user=self.doctor)
            return client.post(
                f"/api/v1/doctor/patients/{self.patient.id}/", {}, format="json"
            ).status_code

        self.assertEqual(sorted(self.run_parallel([add, add])), [200, 201])
        self.assertEqual(DoctorPatient.objects.filter(doctor=self.doctor).count(), 1)

    def test_suspension_serializes_with_patient_add(self):
        def add(client):
            client.force_authenticate(user=self.doctor)
            return client.post(
                f"/api/v1/doctor/patients/{self.patient.id}/", {}, format="json"
            ).status_code

        def suspend(client):
            client.force_authenticate(user=self.admin)
            return client.post(
                f"/api/v1/admin/providers/{self.doctor.id}/suspend/",
                {"reason": "Credential review"},
                format="json",
            ).status_code

        outcomes = self.run_parallel([add, suspend])
        self.assertIn(outcomes[0], [201, 403])
        self.assertEqual(outcomes[1], 200)
        self.assertEqual(
            self.as_user(self.doctor).get("/api/v1/doctor/patients/").status_code, 403
        )
        self.assertEqual(
            self.client.post(f"/api/v1/doctor/patients/{self.patient.id}/").status_code,
            403,
        )


class PatientMediaTests(ClinicFixtures, TestCase):
    def setUp(self):
        from tempfile import TemporaryDirectory

        from django.test import override_settings

        self.setup_domain()
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(PRIVATE_MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def image(self, name="photo.png"):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (60, 80), "#369982").save(buffer, "PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def pdf(self, name="report.pdf", body=None):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from reportlab.pdfgen import canvas

        if body is None:
            buffer = BytesIO()
            document = canvas.Canvas(buffer)
            document.drawString(50, 700, "Synthetic report for testing")
            document.save()
            body = buffer.getvalue()
        return SimpleUploadedFile(name, body, content_type="application/pdf")

    def upload_report(self, user, record_id=None, patient_id=None):
        path = f"/api/v1/patients/{patient_id or self.patient.id}/reports/"
        body = {"file": self.pdf(), "title": "Blood test"}
        if record_id:
            body["record_id"] = str(record_id)
        return self.as_user(user).post(path, body, format="multipart")

    def test_photo_is_private_validated_and_used_on_card(self):
        endpoint = "/api/v1/patients/me/photo/"
        response = self.as_user(self.owner).post(
            endpoint, {"file": self.image()}, format="multipart"
        )
        self.assertEqual(response.status_code, 201, response.data)
        url = response.data["photo_url"]
        self.assertNotIn("storage_name", str(response.data))
        for user in [self.owner, self.doctor, self.pharmacist]:
            photo = self.as_user(user).get(url)
            self.assertEqual(photo.status_code, 200)
            self.assertEqual(photo["Content-Type"], "image/png")
            self.assertIn("no-store", photo["Cache-Control"])
            self.assertTrue(b"".join(photo.streaming_content).startswith(b"\x89PNG"))
        for user in [self.other, self.admin]:
            self.assertEqual(self.as_user(user).get(url).status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(url).status_code, [401, 403])
        self.assertEqual(
            self.as_user(self.owner)
            .post(endpoint, {"file": self.image("disguised.jpg")}, format="multipart")
            .status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                endpoint, {"file": self.pdf()}, format="multipart"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.as_user(self.doctor)
            .post(url, {"file": self.image()}, format="multipart")
            .status_code,
            403,
        )
        card = self.as_user(self.owner).get("/api/v1/patients/me/card/")
        self.assertEqual(card.data["photo_url"], url)
        self.assertEqual(card.data["date_of_birth"], self.patient.date_of_birth)
        pdf = self.client.get("/api/v1/patients/me/card.pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(b"".join(pdf.streaming_content).startswith(b"%PDF"))
        self.apps[self.doctor.id].status = "suspended"
        self.apps[self.doctor.id].save()
        self.assertEqual(self.as_user(self.doctor).get(url).status_code, 403)

    def test_provider_documents_cannot_use_medical_report_kind(self):
        from .models import ProviderDocument

        app = self.apps[self.doctor.id]
        app.status = "pending"
        app.save()
        response = self.as_user(self.doctor).post(
            "/api/v1/provider/application/documents/",
            {"file": self.pdf(), "kind": "report"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProviderDocument.objects.count(), 0)

    def test_reports_are_private_and_doctor_requires_current_approval(self):
        created = self.upload_report(self.owner)
        self.assertEqual(created.status_code, 201, created.data)
        self.assertIsNone(created.data["record_id"])
        self.assertEqual(created.data["uploaded_by"]["id"], str(self.owner.id))
        url = created.data["download_url"]
        for user in [self.owner, self.doctor, self.doctor2]:
            response = self.as_user(user).get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment", response["Content-Disposition"])
            self.assertIn("no-store", response["Cache-Control"])
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))
        for user in [self.other, self.pharmacist, self.admin]:
            self.assertEqual(self.as_user(user).get(url).status_code, 403)
            self.assertEqual(self.upload_report(user).status_code, 403)
        self.assertEqual(
            self.as_user(self.pharmacist)
            .get(f"/api/v1/patients/{self.patient.id}/reports/")
            .status_code,
            403,
        )
        self.apps[self.doctor.id].status = "pending"
        self.apps[self.doctor.id].save()
        self.assertEqual(self.as_user(self.doctor).get(url).status_code, 403)
        self.assertEqual(self.upload_report(self.doctor).status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(url).status_code, [401, 403])

    def test_report_association_checks_patient_and_doctor_and_visits_are_exact(self):
        from .models import MedicalReport

        second = MedicalRecord.objects.create(
            patient=self.patient, doctor=self.doctor2, complaint="Second visit"
        )
        other_patient = Patient.objects.create(
            user=self.other, date_of_birth=date(1990, 1, 1)
        )
        foreign = MedicalRecord.objects.create(
            patient=other_patient, doctor=self.doctor, complaint="Other patient"
        )
        self.assertEqual(self.upload_report(self.doctor, second.id).status_code, 404)
        self.assertEqual(self.upload_report(self.owner, foreign.id).status_code, 404)
        linked = self.upload_report(self.doctor, self.record.id)
        self.assertEqual(linked.status_code, 201, linked.data)
        standalone = self.upload_report(self.owner)
        self.assertEqual(standalone.status_code, 201)
        owner_second = self.upload_report(self.owner, second.id)
        self.assertEqual(owner_second.status_code, 201)
        records = (
            self.as_user(self.owner).get("/api/v1/patients/me/visits/").data["results"]
        )
        by_id = {visit["id"]: visit for visit in records}
        first = by_id[str(self.record.id)]
        self.assertEqual(first["doctor"]["id"], str(self.doctor.id))
        self.assertEqual(first["record"]["doctor_id"], str(self.doctor.id))
        self.assertEqual([r["id"] for r in first["prescriptions"]], [str(self.rx.id)])
        self.assertEqual([r["id"] for r in first["reports"]], [linked.data["id"]])
        self.assertEqual(by_id[str(second.id)]["prescriptions"], [])
        self.assertEqual(
            [r["id"] for r in by_id[str(second.id)]["reports"]],
            [owner_second.data["id"]],
        )
        library = self.client.get("/api/v1/patients/me/reports/").data["results"]
        self.assertEqual(len(library), 3)
        self.assertIn(standalone.data["id"], [r["id"] for r in library])
        self.assertEqual(MedicalReport.objects.count(), 3)

    def test_report_validation_and_rejected_uploads_leave_no_files(self):
        from pathlib import Path

        from .models import MedicalReport

        endpoint = "/api/v1/patients/me/reports/"
        for uploaded in [
            self.pdf(body=b"<script>invalid</script>"),
            self.pdf(body=b"%PDF-1.4" + b"x" * (10 * 1024 * 1024)),
        ]:
            response = self.as_user(self.owner).post(
                endpoint, {"file": uploaded}, format="multipart"
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(MedicalReport.objects.count(), 0)
        self.assertEqual(list(Path(self.media.name).iterdir()), [])
        response = self.client.post(
            endpoint, {"file": self.image(), "title": "X-ray"}, format="multipart"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["content_type"], "image/png")

    def test_linked_prescription_requires_doctors_own_visit(self):
        other_visit = MedicalRecord.objects.create(
            patient=self.patient, doctor=self.doctor2, complaint="Other clinician"
        )
        path = f"/api/v1/patients/{self.patient.id}/prescriptions/"
        body = {
            "record_id": str(self.record.id),
            "valid_until": (timezone.now() + timedelta(days=1)).isoformat(),
            "items": [
                {
                    "medicine": "Example",
                    "dosage": "Prescribed directions",
                    "quantity": "1",
                    "unit": "tablet",
                }
            ],
        }
        response = self.as_user(self.doctor).post(path, body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["record_id"], str(self.record.id))
        body["record_id"] = str(other_visit.id)
        self.assertEqual(self.client.post(path, body, format="json").status_code, 404)

    def test_other_doctor_reports_are_readable_and_append_only(self):
        from .models import MedicalReport

        created = self.upload_report(self.doctor, self.record.id)
        self.assertEqual(created.status_code, 201)
        report = MedicalReport.objects.get(pk=created.data["id"])
        original_values = (
            report.title,
            report.storage_name,
            report.uploaded_by_id,
            report.record_id,
        )
        endpoint = f"/api/v1/patients/{self.patient.id}/reports/"
        listed = self.as_user(self.doctor2).get(endpoint)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            listed.data["results"][0]["uploaded_by"]["id"], str(self.doctor.id)
        )
        download = self.client.get(created.data["download_url"])
        self.assertEqual(download.status_code, 200)
        self.assertTrue(b"".join(download.streaming_content).startswith(b"%PDF"))
        for method in [self.client.patch, self.client.delete]:
            self.assertEqual(
                method(endpoint, {"title": "Changed"}, format="json").status_code, 405
            )
            self.assertEqual(
                method(created.data["download_url"], {}, format="json").status_code, 405
            )
        self.assertEqual(
            self.upload_report(self.doctor2, self.record.id).status_code, 404
        )
        self.assertEqual(self.upload_report(self.doctor2).status_code, 201)
        report.refresh_from_db()
        self.assertEqual(
            (
                report.title,
                report.storage_name,
                report.uploaded_by_id,
                report.record_id,
            ),
            original_values,
        )
