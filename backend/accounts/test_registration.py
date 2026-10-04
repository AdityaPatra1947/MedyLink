from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from clinic.models import Patient, ProviderApplication, ProviderDocument, ProviderReview
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import User

PASSWORD = "Registration-test-passphrase-93742!"
REGISTER = "/api/v1/auth/register/"


class RegistrationReviewTests(TestCase):
    def setUp(self):
        self.storage = TemporaryDirectory(prefix="medylink-registration-")
        self.addCleanup(self.storage.cleanup)
        setting = override_settings(PRIVATE_MEDIA_ROOT=Path(self.storage.name))
        setting.enable()
        self.addCleanup(setting.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        csrf = self.client.get("/api/v1/auth/csrf/").data["csrfToken"]
        self.client.credentials(HTTP_X_CSRFTOKEN=csrf)
        self.admin = User.objects.create_user(
            "reviewer@example.com",
            PASSWORD,
            name="Reviewer",
            role="admin",
            email_verified_at=timezone.now(),
        )

    def image(self, name="credential.png"):
        content = BytesIO()
        Image.new("RGB", (12, 12), color="white").save(content, format="PNG")
        return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")

    def payload(self, role="patient", email="registered@example.com"):
        data = {
            "name": "Registered Person",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "role": role,
            "consent": True,
            "privacy_version": "1.0",
        }
        if role == "patient":
            data.update(date_of_birth="1990-01-02")
        else:
            data.update(
                registration_number="reg-123",
                registering_body="State Council",
                practice_address="1 Clinic Road",
                credential_documents=[self.image()],
            )
            if role == "doctor":
                data.update(qualification="MBBS", specialty="General Medicine")
            else:
                data.update(
                    shop_name="Community Pharmacy",
                    shop_license="shop-123",
                    shop_license_expires=(
                        timezone.localdate() + timedelta(days=365)
                    ).isoformat(),
                )
        return data

    def register_provider(self, role="doctor", email="provider@example.com", **extra):
        data = self.payload(role, email)
        data.update(extra)
        response = self.client.post(REGISTER, data, format="multipart")
        self.assertEqual(response.status_code, 202, response.data)
        return ProviderApplication.objects.get(provider__email=email)

    def review(self, app, decision="approve"):
        self.client.force_authenticate(user=self.admin)
        data = {"reason": "Credential identity reviewed"}
        if decision == "approve":
            data.update(
                evidence_reviewed="Professional registration and uploaded evidence checked",
                valid_until=(timezone.now() + timedelta(days=30)).isoformat(),
            )
        return self.client.post(
            f"/api/v1/admin/provider-applications/{app.id}/{decision}/",
            data,
            format="json",
        )

    def make_verified(self, app):
        app.provider.email_verified_at = timezone.now()
        app.provider.save(update_fields=["email_verified_at"])
        app.documents.filter(kind="credential").update(status="validated")

    def test_patient_json_registration_creates_adult_profile_and_optional_fields(self):
        data = self.payload()
        data.update(
            phone="+91 9000000000",
            gender="prefer_not_to_say",
            address="Patient address",
            emergency_contact="Trusted contact",
        )
        response = self.client.post(REGISTER, data, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        user = User.objects.get(email=data["email"])
        patient = Patient.objects.get(user=user)
        self.assertEqual(patient.date_of_birth, date(1990, 1, 2))
        self.assertEqual(patient.gender, "prefer_not_to_say")
        self.assertEqual(patient.phone, user.phone)
        self.assertEqual(patient.blood_group, "unknown")
        self.assertEqual(patient.emergency_contact, "Trusted contact")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(ProviderApplication.objects.filter(provider=user).exists())
        self.assertEqual(set(response.data), {"detail"})

    def test_registration_requires_matching_passwords_adult_dob_and_valid_gender(self):
        for change in [
            {"password_confirm": None},
            {"password_confirm": "different-password"},
            {"date_of_birth": None},
            {"date_of_birth": timezone.localdate().isoformat()},
            {"gender": "invalid"},
            {"phone": "1" * 31},
        ]:
            with self.subTest(change=change):
                data = self.payload()
                data.update(change)
                response = self.client.post(REGISTER, data, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        data = self.payload()
        del data["password_confirm"]
        self.assertEqual(
            self.client.post(REGISTER, data, format="json").status_code, 400
        )
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Patient.objects.exists())

    def test_doctor_multipart_registers_pending_application_and_private_typed_files(
        self,
    ):
        app = self.register_provider(
            clinic_name="Neighbourhood Clinic",
            years_experience="7",
            phone="+91 9000000001",
            photo=self.image("portrait.png"),
        )
        self.assertEqual(app.status, "pending")
        self.assertEqual(app.qualification, "MBBS")
        self.assertEqual(app.clinic_name, "Neighbourhood Clinic")
        self.assertEqual(app.years_experience, 7)
        self.assertEqual(app.registration_number, "REG-123")
        self.assertEqual(app.contact_phone, app.provider.phone)
        self.assertEqual(
            set(app.documents.values_list("kind", flat=True)), {"credential", "photo"}
        )
        self.assertFalse(app.documents.exclude(status="quarantined").exists())
        for document in app.documents.all():
            self.assertTrue((Path(self.storage.name) / document.storage_name).is_file())
            self.assertGreater(document.size_bytes, 0)
        response = self.client.get(
            f"/api/v1/provider-documents/{app.documents.first().id}/download/"
        )
        self.assertEqual(response.status_code, 401)

    def test_pharmacy_registration_and_required_professional_fields(self):
        app = self.register_provider("pharmacist", opening_hours="Mon–Sat 09:00–18:00")
        self.assertEqual(app.shop_name, "Community Pharmacy")
        self.assertEqual(app.shop_license, "SHOP-123")
        self.assertEqual(app.opening_hours, "Mon–Sat 09:00–18:00")
        for role, missing in [
            ("doctor", "qualification"),
            ("doctor", "specialty"),
            ("doctor", "registration_number"),
            ("doctor", "registering_body"),
            ("doctor", "practice_address"),
            ("doctor", "credential_documents"),
            ("pharmacist", "shop_name"),
            ("pharmacist", "shop_license"),
            ("pharmacist", "shop_license_expires"),
        ]:
            with self.subTest(role=role, missing=missing):
                data = self.payload(role, email="missing@example.com")
                del data[missing]
                self.assertEqual(
                    self.client.post(REGISTER, data, format="multipart").status_code,
                    400,
                )
        data = self.payload("pharmacist", email="expired@example.com")
        data["shop_license_expires"] = (
            timezone.localdate() - timedelta(days=1)
        ).isoformat()
        self.assertEqual(
            self.client.post(REGISTER, data, format="multipart").status_code, 400
        )

    def test_file_limits_types_and_photo_rules_are_enforced_before_persistence(self):
        cases = [
            {
                "credential_documents": [
                    SimpleUploadedFile(
                        "fake.pdf",
                        b"<script>unsafe</script>",
                        content_type="application/pdf",
                    )
                ]
            },
            {"credential_documents": [self.image(f"proof-{n}.png") for n in range(6)]},
            {
                "photo": SimpleUploadedFile(
                    "photo.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"
                )
            },
            {"years_experience": "81"},
            {
                "credential_documents": [
                    SimpleUploadedFile(
                        "oversized.pdf", b"%PDF-1.4\n" + b"x" * (5 * 1024 * 1024)
                    )
                ]
            },
        ]
        for extra in cases:
            with self.subTest(fields=list(extra)):
                data = self.payload("doctor")
                data.update(extra)
                self.assertEqual(
                    self.client.post(REGISTER, data, format="multipart").status_code,
                    400,
                )
        self.assertFalse(ProviderApplication.objects.exists())
        self.assertEqual(list(Path(self.storage.name).iterdir()), [])

    def test_email_failure_rolls_back_registration_and_removes_private_files(self):
        with patch(
            "accounts.registration.send_account_email",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            response = self.client.post(
                REGISTER, self.payload("doctor"), format="multipart"
            )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(User.objects.filter(email="registered@example.com").exists())
        self.assertFalse(ProviderApplication.objects.exists())
        self.assertFalse(ProviderDocument.objects.exists())
        self.assertEqual(list(Path(self.storage.name).iterdir()), [])

    def test_later_file_failure_rolls_back_earlier_file_and_database_rows(self):
        original = ProviderDocument.objects.create
        counter = 0

        def create_document(**kwargs):
            nonlocal counter
            counter += 1
            if counter == 2:
                raise OSError("Simulated file metadata failure")
            return original(**kwargs)

        data = self.payload("doctor")
        data["credential_documents"].append(self.image("second.png"))
        with patch(
            "clinic.uploads.ProviderDocument.objects.create",
            side_effect=create_document,
        ):
            response = self.client.post(REGISTER, data, format="multipart")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(User.objects.filter(email=data["email"]).exists())
        self.assertFalse(ProviderDocument.objects.exists())
        self.assertEqual(list(Path(self.storage.name).iterdir()), [])

    def test_unverified_provider_cannot_be_approved_even_with_validated_evidence(self):
        app = self.register_provider()
        app.documents.update(status="validated")
        self.assertEqual(self.review(app).status_code, 400)
        app.refresh_from_db()
        self.assertEqual(app.status, "pending")
        self.assertFalse(ProviderReview.objects.exists())

    def test_photo_alone_never_approves_and_all_credential_evidence_is_required(self):
        app = self.register_provider(photo=self.image("portrait.png"))
        self.make_verified(app)
        app.documents.filter(kind="credential").update(kind="photo")
        self.assertEqual(self.review(app).status_code, 400)
        credential = app.documents.order_by("created_at").first()
        ProviderDocument.objects.filter(pk=credential.pk).update(
            kind="credential", status="quarantined"
        )
        self.assertEqual(self.review(app).status_code, 400)
        app.documents.filter(kind="credential").update(status="validated")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.review(app)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "approved")

    def test_review_emails_are_after_commit_and_delivery_failure_keeps_decision(self):
        app = self.register_provider()
        self.make_verified(app)
        before = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.review(app)
            self.assertEqual(len(mail.outbox), before)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), before + 1)
        self.assertIn("approved", mail.outbox[-1].body)
        with patch(
            "clinic.notifications.send_mail", side_effect=OSError("SMTP unavailable")
        ):
            with self.assertLogs("clinic.notifications", level="WARNING"):
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.review(app, "reject")
        self.assertEqual(response.status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.status, "rejected")
        self.assertEqual(app.reviews.count(), 2)

    def test_admin_filters_search_history_and_invalid_filters(self):
        doctor = self.register_provider("doctor", "doctor@example.com")
        pharmacy = self.register_provider("pharmacist", "pharmacy@example.com")
        self.client.force_authenticate(user=self.admin)
        path = "/api/v1/admin/provider-applications/"
        response = self.client.get(
            path + "?role=doctor&status=pending&search=doctor%40example.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["results"]], [str(doctor.id)]
        )
        row = response.data["results"][0]
        self.assertEqual(row["provider_email"], "doctor@example.com")
        self.assertFalse(row["email_verified"])
        self.assertEqual(row["documents"][0]["kind"], "credential")
        self.assertNotIn("storage_name", str(row))
        self.assertEqual(self.client.get(path + "?role=patient").status_code, 400)
        self.assertEqual(self.client.get(path + "?status=invalid").status_code, 400)
        self.assertEqual(
            self.client.get(path + "?search=" + "x" * 101).status_code, 400
        )
        pharmacy.status = "approved"
        pharmacy.valid_until = timezone.now() - timedelta(hours=1)
        pharmacy.save()
        expired = self.client.get(path + "?role=pharmacist&status=expired")
        self.assertEqual(
            [row["id"] for row in expired.data["results"]], [str(pharmacy.id)]
        )
        self.assertEqual(
            self.client.get(path + "?role=pharmacist&status=approved").data["results"],
            [],
        )
        self.make_verified(doctor)
        self.client.force_authenticate(user=doctor.provider)
        resubmission = self.client.post(
            "/api/v1/provider/application/",
            {
                "qualification": "MD",
                "specialty": "Internal Medicine",
                "registration_number": "REG-123",
                "registering_body": "State Council",
                "practice_address": "New clinic address",
                "clinic_name": "Updated clinic",
                "years_experience": 8,
                "opening_hours": "Weekdays",
            },
            format="json",
        )
        self.assertEqual(resubmission.status_code, 201, resubmission.data)
        self.client.force_authenticate(user=self.admin)
        detail = self.client.get(path + resubmission.data["id"] + "/")
        self.assertEqual(detail.data["qualification"], "MD")
        self.assertEqual(detail.data["history"][0]["id"], str(doctor.id))
        self.assertFalse(detail.data["history"][0]["is_current"])
        self.client.force_authenticate(user=doctor.provider)
        self.assertEqual(self.client.get(path).status_code, 403)

    def test_existing_document_upload_uses_same_validation_and_private_kind(self):
        app = self.register_provider()
        self.make_verified(app)
        self.client.force_authenticate(user=app.provider)
        path = "/api/v1/provider/application/documents/"
        response = self.client.post(
            path, {"kind": "photo", "file": self.image("photo.png")}, format="multipart"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["kind"], "photo")
        self.assertEqual(
            self.client.post(
                path,
                {"kind": "photo", "file": self.image("second.png")},
                format="multipart",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                path, {"kind": "invalid", "file": self.image()}, format="multipart"
            ).status_code,
            400,
        )
