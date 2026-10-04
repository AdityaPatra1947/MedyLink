import re
from datetime import timedelta

from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import UntypedToken

from .models import (
    AuthSession,
    EmailVerificationChallenge,
    SecurityEvent,
    User,
)
from .services import digest, email_code_digest

PASSWORD = "A-test-passphrase-93742!"
PREFIX = "/api/v1/auth/"


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = self.browser()

    def browser(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get(PREFIX + "csrf/")
        self.assertEqual(csrf.status_code, 200)
        client.credentials(HTTP_X_CSRFTOKEN=csrf.data["csrfToken"])
        return client

    def user(self, role="patient", email="person@example.com", verified=True):
        return User.objects.create_user(
            email=email,
            password=PASSWORD,
            name="Test Person",
            role=role,
            email_verified_at=timezone.now() if verified else None,
        )

    def login(self, user, client=None):
        return (client or self.client).post(
            PREFIX + "login/",
            {"email": user.email, "password": PASSWORD},
            format="json",
        )

    def mail_token(self):
        return re.search(r"\?token=([A-Za-z0-9_-]+)", mail.outbox[-1].body).group(1)

    def mail_code(self):
        return re.search(
            r"Your verification code: ([0-9]{6})", mail.outbox[-1].body
        ).group(1)

    def test_register_normalizes_email_hashes_password_and_requires_consent(self):
        data = {
            "name": "New Patient",
            "email": "NEW@EXAMPLE.COM",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "role": "patient",
            "consent": True,
            "date_of_birth": "1990-01-01",
        }
        response = self.client.post(PREFIX + "register/", data, format="json")
        self.assertEqual(response.status_code, 202)
        user = User.objects.get(email="new@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertIsNotNone(user.storage_consent_at)
        self.assertIsNone(user.email_verified_at)
        self.assertNotIn("token", response.data)
        raw = self.mail_code()
        challenge = EmailVerificationChallenge.objects.get(user=user)
        self.assertEqual(
            challenge.digest, email_code_digest(user.id, challenge.nonce, raw)
        )
        self.assertNotEqual(challenge.digest, digest(raw))
        self.assertNotEqual(challenge.digest, raw)
        duplicate = self.client.post(PREFIX + "register/", data, format="json")
        self.assertEqual(duplicate.data, response.data)
        self.assertEqual(User.objects.count(), 1)
        data.update(email="other@example.com", consent=False)
        self.assertEqual(
            self.client.post(PREFIX + "register/", data, format="json").status_code, 400
        )
        data.update(consent=True, role="admin")
        self.assertEqual(
            self.client.post(PREFIX + "register/", data, format="json").status_code, 400
        )

    def test_case_insensitive_email_uniqueness_is_in_database(self):
        self.user(email="person@example.com")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(email="PERSON@example.com", name="Duplicate")

    def test_verification_resend_invalidates_previous_code_and_is_single_use(self):
        user = self.user(verified=False)
        self.assertEqual(self.login(user).status_code, 401)
        self.client.post(
            PREFIX + "resend-verification/", {"email": user.email}, format="json"
        )
        old = self.mail_code()
        EmailVerificationChallenge.objects.filter(user=user).update(
            created_at=timezone.now() - timedelta(seconds=61)
        )
        self.client.post(
            PREFIX + "resend-verification/", {"email": user.email}, format="json"
        )
        current = self.mail_code()
        self.assertNotEqual(old, current)
        self.assertEqual(
            self.client.post(
                PREFIX + "verify-email/",
                {"email": user.email, "code": old},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                PREFIX + "verify-email/",
                {"email": user.email, "code": current},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                PREFIX + "verify-email/",
                {"email": user.email, "code": current},
                format="json",
            ).status_code,
            400,
        )
        user.refresh_from_db()
        self.assertTrue(user.email_verified)

    def test_authentication_mutations_reject_missing_csrf(self):
        unsafe = APIClient(enforce_csrf_checks=True)
        for endpoint in [
            "register/",
            "login/",
            "refresh/",
            "logout/",
            "forgot-password/",
            "verify-email/",
            "resend-verification/",
            "reset-password/",
        ]:
            self.assertEqual(
                unsafe.post(PREFIX + endpoint, {}, format="json").status_code,
                403,
                endpoint,
            )

    def test_login_cookie_security_and_logout_revokes_copied_access(self):
        user = self.user()
        response = self.login(user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"user"})
        self.assertTrue(response.cookies["access_token"]["httponly"])
        self.assertTrue(response.cookies["refresh_token"]["httponly"])
        self.assertEqual(response.cookies["access_token"]["samesite"], "Lax")
        access = response.cookies["access_token"].value
        self.assertEqual(self.client.get(PREFIX + "me/").status_code, 200)
        self.assertEqual(
            self.client.post(PREFIX + "logout/", {}, format="json").status_code, 200
        )
        copied = self.browser()
        copied.cookies["access_token"] = access
        self.assertEqual(copied.get(PREFIX + "me/").status_code, 401)

    def test_refresh_rotates_without_extending_absolute_expiry_and_replay_revokes(self):
        user = self.user()
        self.login(user)
        original = self.client.cookies["refresh_token"].value
        original_exp = UntypedToken(original)["exp"]
        response = self.client.post(PREFIX + "refresh/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        rotated = self.client.cookies["refresh_token"].value
        self.assertNotEqual(original, rotated)
        self.assertEqual(UntypedToken(rotated)["exp"], original_exp)
        replay = self.browser()
        replay.cookies["refresh_token"] = original
        self.assertEqual(
            replay.post(PREFIX + "refresh/", {}, format="json").status_code, 401
        )
        self.assertEqual(self.client.get(PREFIX + "me/").status_code, 401)

    def test_session_absolute_expiry_and_deactivated_user_checked_on_access(self):
        user = self.user()
        self.login(user)
        AuthSession.objects.filter(user=user).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.client.get(PREFIX + "me/").status_code, 401)
        self.assertEqual(
            self.client.post(PREFIX + "refresh/", {}, format="json").status_code, 401
        )
        self.login(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(PREFIX + "me/").status_code, 401)

    def test_reset_is_purpose_bound_single_use_and_revokes_sessions(self):
        user = self.user()
        self.login(user)
        copied = self.browser()
        copied.cookies["access_token"] = self.client.cookies["access_token"].value
        self.client.post(
            PREFIX + "forgot-password/", {"email": user.email}, format="json"
        )
        raw = self.mail_token()
        self.assertEqual(
            self.client.post(
                PREFIX + "verify-email/", {"token": raw}, format="json"
            ).status_code,
            400,
        )
        data = {"token": raw, "password": "New-long-passphrase-87423!"}
        self.assertEqual(
            self.client.post(
                PREFIX + "reset-password/", data, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                PREFIX + "reset-password/", data, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(copied.get(PREFIX + "me/").status_code, 401)
        user.refresh_from_db()
        self.assertTrue(user.check_password(data["password"]))

    def test_recovery_unknown_email_has_same_response(self):
        user = self.user()
        known = self.client.post(
            PREFIX + "forgot-password/", {"email": user.email}, format="json"
        )
        unknown = self.client.post(
            PREFIX + "forgot-password/", {"email": "nobody@example.com"}, format="json"
        )
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data, unknown.data)

    def test_session_lists_and_revocation_are_owner_scoped(self):
        user = self.user()
        other = self.user(email="other@example.com")
        self.login(user)
        first_session = AuthSession.objects.get(user=user)
        other_browser = self.browser()
        self.login(other, other_browser)
        response = other_browser.delete(PREFIX + f"sessions/{first_session.id}/")
        self.assertEqual(response.status_code, 404)
        listing = self.client.get(PREFIX + "sessions/")
        self.assertEqual(len(listing.data["results"]), 1)
        self.assertTrue(listing.data["results"][0]["current"])
        self.assertEqual(
            self.client.delete(PREFIX + f"sessions/{first_session.id}/").status_code,
            204,
        )
        first_session.refresh_from_db()
        self.assertIsNotNone(first_session.revoked_at)

    def test_logout_all_invalidates_other_devices(self):
        user = self.user()
        self.login(user)
        other = self.browser()
        self.login(user, other)
        self.assertEqual(
            self.client.post(PREFIX + "logout-all/", {}, format="json").status_code, 200
        )
        self.assertEqual(other.get(PREFIX + "me/").status_code, 401)

    def test_all_verified_roles_sign_in_directly_and_refresh(self):
        for role in User.Role.values:
            with self.subTest(role=role):
                user = self.user(role=role, email=f"{role}@example.com")
                client = self.browser()
                response = self.login(user, client)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(set(response.data), {"user"})
                self.assertEqual(
                    set(response.data["user"]),
                    {
                        "id",
                        "account_id",
                        "name",
                        "email",
                        "role",
                        "phone",
                        "email_verified",
                    },
                )
                self.assertEqual(response.data["user"]["role"], role)
                self.assertEqual(
                    set(response.cookies), {"access_token", "refresh_token"}
                )
                self.assertTrue(response.cookies["access_token"]["httponly"])
                self.assertTrue(response.cookies["refresh_token"]["httponly"])
                self.assertEqual(AuthSession.objects.filter(user=user).count(), 1)
                self.assertEqual(client.get(PREFIX + "me/").status_code, 200)
                refresh = client.post(PREFIX + "refresh/", {}, format="json")
                self.assertEqual(refresh.status_code, 200)
                self.assertEqual(set(refresh.data), {"user"})

    def test_all_roles_still_require_correct_password_verified_email_and_active_account(
        self,
    ):
        for role in User.Role.values:
            with self.subTest(role=role):
                user = self.user(
                    role=role, email=f"blocked-{role}@example.com", verified=False
                )
                client = self.browser()
                self.assertEqual(self.login(user, client).status_code, 401)
                user.email_verified_at = timezone.now()
                user.save(update_fields=["email_verified_at"])
                wrong = client.post(
                    PREFIX + "login/",
                    {"email": user.email, "password": "Wrong-passphrase-82732!"},
                    format="json",
                )
                self.assertEqual(wrong.status_code, 401)
                user.is_active = False
                user.save(update_fields=["is_active"])
                self.assertEqual(self.login(user, client).status_code, 401)
                self.assertFalse(AuthSession.objects.filter(user=user).exists())

    def test_removed_authenticator_endpoints_and_legacy_cookie_cannot_authenticate(
        self,
    ):
        for endpoint in ["setup/", "confirm/", "verify/", "recovery-codes/"]:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(
                    PREFIX + "mfa/" + endpoint, {}, format="json"
                )
                self.assertEqual(response.status_code, 404)
        self.client.cookies["mfa_challenge"] = "legacy-restricted-cookie"
        self.assertEqual(self.client.get(PREFIX + "me/").status_code, 401)
        self.assertEqual(
            self.client.post(PREFIX + "refresh/", {}, format="json").status_code, 401
        )

    def test_provider_password_reset_allows_direct_sign_in_and_revokes_old_session(
        self,
    ):
        user = self.user(role="pharmacist")
        self.login(user)
        original = AuthSession.objects.get(user=user)
        self.client.post(
            PREFIX + "forgot-password/", {"email": user.email}, format="json"
        )
        response = self.client.post(
            PREFIX + "reset-password/",
            {"token": self.mail_token(), "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        original.refresh_from_db()
        self.assertIsNotNone(original.revoked_at)
        signed_in = self.login(user)
        self.assertEqual(signed_in.status_code, 200)
        self.assertEqual(set(signed_in.data), {"user"})
        self.assertEqual(self.client.get(PREFIX + "me/").status_code, 200)

    def test_admin_audit_combines_paginated_safe_security_and_clinical_metadata(self):
        from datetime import date

        from clinic.models import AuditEvent, Patient

        patient_user = self.user(email="private-patient@example.com")
        patient = Patient.objects.create(
            user=patient_user, date_of_birth=date(1990, 1, 1)
        )
        clinical = AuditEvent.objects.create(
            actor=patient_user,
            patient=patient,
            event="record.read",
            resource_id="PRIVATE_MEDICAL_NOTE",
            request_id="clinical-audit-case",
        )
        security = SecurityEvent.objects.create(
            user=patient_user,
            event="password_reset",
            request_id="security-audit-case",
            metadata={
                "token": "SECRET_RESET_TOKEN",
                "email": patient_user.email,
                "notes": "PRIVATE_MEDICAL_NOTE",
            },
        )
        SecurityEvent.objects.bulk_create(
            [
                SecurityEvent(user=patient_user, event="login", outcome="success")
                for _ in range(51)
            ]
        )
        admin = self.user(role="admin", email="admin@example.com")
        self.assertEqual(self.login(admin).status_code, 200)
        first = self.client.get("/api/v1/admin/audit/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.data["results"]), 50)
        self.assertEqual(first.data["next"], 2)
        second = self.client.get("/api/v1/admin/audit/?page=2")
        self.assertEqual(second.status_code, 200)
        rows = first.data["results"] + second.data["results"]
        ids = [row["id"] for row in rows]
        self.assertIn(str(clinical.id), ids)
        self.assertIn(str(security.id), ids)
        self.assertEqual(len(ids), len(set(ids)))
        for row in rows:
            self.assertEqual(
                set(row),
                {"id", "actor_name", "event", "outcome", "created_at", "request_id"},
            )
        for secret_value in [
            patient_user.email,
            "SECRET_RESET_TOKEN",
            "PRIVATE_MEDICAL_NOTE",
            str(patient.id),
        ]:
            self.assertNotIn(secret_value, str(rows))
        patient_browser = self.browser()
        self.login(patient_user, patient_browser)
        self.assertEqual(patient_browser.get("/api/v1/admin/audit/").status_code, 403)
        own_history = patient_browser.get("/api/v1/patients/me/access-history/")
        self.assertEqual(own_history.status_code, 200)
        self.assertNotIn("password_reset", str(own_history.data))
