import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.core import mail
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AccountToken, EmailVerificationChallenge, SecurityEvent, User
from .services import digest, email_code_digest

PREFIX = "/api/v1/auth/"
PASSWORD = "Verification-testing-passphrase-93742!"


class EmailCodeFixtures:
    def browser(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get(PREFIX + "csrf/").data["csrfToken"]
        client.credentials(HTTP_X_CSRFTOKEN=csrf)
        return client

    def setUp(self):
        self.client = self.browser()
        self.user = User.objects.create_user(
            "verify@example.com",
            PASSWORD,
            name="Verify Patient",
            role="patient",
        )

    def issue(self, user=None, number=123456):
        user = user or self.user
        with patch("accounts.services.secrets.randbelow", return_value=number):
            response = self.client.post(
                PREFIX + "resend-verification/",
                {"email": user.email},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        code = re.search(
            r"Your verification code: ([0-9]{6})", mail.outbox[-1].body
        ).group(1)
        return code, EmailVerificationChallenge.objects.filter(user=user).latest(
            "created_at"
        )

    def verify(self, code, email=None, client=None):
        return (client or self.client).post(
            PREFIX + "verify-email/",
            {"email": email or self.user.email, "code": code},
            format="json",
        )

    def allow_resend(self, challenge):
        challenge.created_at = timezone.now() - timedelta(seconds=61)
        challenge.save(update_fields=["created_at"])


class EmailVerificationCodeTests(EmailCodeFixtures, TestCase):
    def test_leading_zero_code_is_keyed_nonce_bound_and_single_use(self):
        before = timezone.now()
        code, challenge = self.issue(number=7)
        self.assertEqual(code, "000007")
        self.assertEqual(
            challenge.digest, email_code_digest(self.user.id, challenge.nonce, code)
        )
        self.assertNotEqual(challenge.digest, code)
        self.assertNotEqual(challenge.digest, digest(code))
        self.assertGreaterEqual(challenge.expires_at, before + timedelta(minutes=10))
        self.assertLessEqual(
            challenge.expires_at, timezone.now() + timedelta(minutes=10)
        )
        self.assertIn("10 minutes", mail.outbox[-1].body)
        self.assertNotIn("http", mail.outbox[-1].body)
        self.assertNotIn("?token=", mail.outbox[-1].body)
        self.assertEqual(
            self.verify(code, email=self.user.email.upper()).status_code, 200
        )
        self.assertEqual(self.verify(code).status_code, 400)
        self.user.refresh_from_db()
        challenge.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertIsNotNone(challenge.used_at)
        self.assertFalse(
            AccountToken.objects.filter(
                user=self.user, purpose=AccountToken.Purpose.VERIFY_EMAIL
            ).exists()
        )

    def test_six_ascii_digits_must_be_a_string_and_preserve_zeros(self):
        code, challenge = self.issue(number=0)
        for invalid in [
            "00000",
            "0000000",
            "abcdef",
            "１２３４５６",
            "00000\n",
            123456,
            " 000000",
        ]:
            with self.subTest(value=invalid):
                self.assertEqual(self.verify(invalid).status_code, 400)
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 0)
        self.assertEqual(self.verify(code).status_code, 200)

    def test_wrong_email_and_unknown_account_do_not_verify_or_reveal_status(self):
        code, first = self.issue(number=111111)
        other = User.objects.create_user(
            "other-code@example.com",
            PASSWORD,
            name="Other Patient",
            role="patient",
        )
        _, second = self.issue(other, number=222222)
        wrong = self.verify(code, email=other.email)
        unknown = self.verify(code, email="unknown@example.com")
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(wrong.data["code"], unknown.data["code"])
        self.assertEqual(wrong.data["detail"], unknown.data["detail"])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.attempts, 0)
        self.assertEqual(second.attempts, 1)
        self.assertFalse(User.objects.filter(email_verified_at__isnull=False).exists())

    def test_identical_codes_for_different_users_have_distinct_digests(self):
        code, first = self.issue(number=42)
        other = User.objects.create_user(
            "nonce@example.com",
            PASSWORD,
            name="Nonce Patient",
            role="patient",
        )
        same, second = self.issue(other, number=42)
        self.assertEqual(code, same)
        self.assertNotEqual(first.nonce, second.nonce)
        self.assertNotEqual(first.digest, second.digest)

    def test_expired_and_used_codes_have_generic_failure_and_do_not_verify(self):
        code, challenge = self.issue()
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.save(update_fields=["expires_at"])
        expired = self.verify(code)
        self.assertEqual(expired.status_code, 400)
        challenge.expires_at = timezone.now() + timedelta(minutes=10)
        challenge.used_at = timezone.now()
        challenge.save(update_fields=["expires_at", "used_at"])
        used = self.verify(code)
        self.assertEqual(used.status_code, 400)
        self.assertEqual(expired.data["detail"], used.data["detail"])
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_five_wrong_attempts_commit_and_lock_out_even_the_correct_code(self):
        code, challenge = self.issue(number=111111)
        for attempt in range(1, 6):
            self.assertEqual(self.verify("999999").status_code, 400)
            challenge.refresh_from_db()
            self.assertEqual(challenge.attempts, attempt)
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertEqual(self.verify("999999").status_code, 400)
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 5)
        self.assertIsNone(challenge.used_at)
        self.allow_resend(challenge)
        replacement, fresh = self.issue(number=222222)
        self.assertEqual(fresh.attempts, 0)
        self.assertEqual(self.verify(replacement).status_code, 200)
        for event in SecurityEvent.objects.filter(user=self.user):
            self.assertNotIn("111111", str(event.metadata))
            self.assertNotIn("999999", str(event.metadata))
            self.assertNotIn("222222", str(event.metadata))

    def test_resend_cooldown_has_same_public_response_for_all_account_states(self):
        code, challenge = self.issue()
        count = len(mail.outbox)
        pending = self.client.post(
            PREFIX + "resend-verification/", {"email": self.user.email}, format="json"
        )
        unknown = self.client.post(
            PREFIX + "resend-verification/",
            {"email": "unknown@example.com"},
            format="json",
        )
        verified = User.objects.create_user(
            "verified@example.com",
            PASSWORD,
            name="Verified Patient",
            role="patient",
            email_verified_at=timezone.now(),
        )
        already_verified = self.client.post(
            PREFIX + "resend-verification/", {"email": verified.email}, format="json"
        )
        self.assertEqual(pending.data, unknown.data)
        self.assertEqual(pending.data, already_verified.data)
        self.assertEqual(pending.data["resend_after"], 60)
        self.assertEqual(len(mail.outbox), count)
        self.assertEqual(EmailVerificationChallenge.objects.count(), 1)
        challenge.refresh_from_db()
        self.assertIsNone(challenge.used_at)
        self.assertEqual(self.verify(code).status_code, 200)

    def test_resend_invalidates_previous_code_even_if_random_source_repeats_digits(
        self,
    ):
        old, previous = self.issue(number=0)
        self.allow_resend(previous)
        current, challenge = self.issue(number=0)
        self.assertNotEqual(current, old)
        self.assertNotEqual(previous.nonce, challenge.nonce)
        previous.refresh_from_db()
        self.assertIsNotNone(previous.used_at)
        self.assertEqual(self.verify(old).status_code, 400)
        self.assertEqual(self.verify(current).status_code, 200)

    def test_smtp_failure_preserves_previous_code_and_resend_time(self):
        code, previous = self.issue()
        self.allow_resend(previous)
        created_at = previous.created_at
        with patch(
            "accounts.services.send_mail", side_effect=OSError("SMTP unavailable")
        ):
            response = self.client.post(
                PREFIX + "resend-verification/",
                {"email": self.user.email},
                format="json",
            )
        self.assertEqual(response.status_code, 500)
        previous.refresh_from_db()
        self.assertIsNone(previous.used_at)
        self.assertEqual(previous.created_at, created_at)
        self.assertEqual(previous.attempts, 0)
        self.assertEqual(EmailVerificationChallenge.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.verify(code).status_code, 200)

    def test_old_verification_link_is_rejected_and_retired_on_resend(self):
        raw = "legacy-verification-token-" + "x" * 24
        legacy = AccountToken.objects.create(
            user=self.user,
            purpose=AccountToken.Purpose.VERIFY_EMAIL,
            digest=digest(raw),
            expires_at=timezone.now() + timedelta(hours=24),
        )
        response = self.client.post(
            PREFIX + "verify-email/", {"token": raw}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)
        code, _ = self.issue()
        legacy.refresh_from_db()
        self.assertIsNotNone(legacy.used_at)
        self.assertEqual(self.verify(code).status_code, 200)

    def test_reset_link_still_works_and_cannot_substitute_for_email_verification(self):
        code, challenge = self.issue()
        response = self.client.post(
            PREFIX + "forgot-password/", {"email": self.user.email}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        raw = re.search(r"\?token=([A-Za-z0-9_-]+)", mail.outbox[-1].body).group(1)
        self.assertIn("/reset-password?token=", mail.outbox[-1].body)
        self.assertEqual(self.verify(raw).status_code, 400)
        self.assertEqual(
            self.client.post(
                PREFIX + "reset-password/",
                {"token": code, "password": PASSWORD},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                PREFIX + "reset-password/",
                {"token": raw, "password": PASSWORD},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                PREFIX + "reset-password/",
                {"token": raw, "password": PASSWORD},
                format="json",
            ).status_code,
            400,
        )
        self.user.refresh_from_db()
        challenge.refresh_from_db()
        self.assertFalse(self.user.email_verified)
        self.assertIsNone(challenge.used_at)
        self.assertEqual(self.verify(code).status_code, 200)
        login = self.client.post(
            PREFIX + "login/",
            {"email": self.user.email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(set(login.data), {"user"})
        self.assertEqual(self.client.get(PREFIX + "me/").status_code, 200)


@skipUnless(
    connection.vendor == "postgresql",
    "Requires isolated PostgreSQL for row-lock guarantees.",
)
class EmailVerificationConcurrencyTests(EmailCodeFixtures, TransactionTestCase):
    def parallel(self, operations):
        barrier = Barrier(len(operations))

        def execute(operation):
            close_old_connections()
            try:
                client = self.browser()
                barrier.wait(timeout=10)
                return operation(client)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            return list(executor.map(execute, operations))

    def test_same_code_concurrent_verification_succeeds_only_once(self):
        code, challenge = self.issue()
        results = self.parallel(
            [
                lambda client: self.verify(code, client=client).status_code,
                lambda client: self.verify(code, client=client).status_code,
            ]
        )
        self.assertEqual(sorted(results), [200, 400])
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.used_at)
        self.assertEqual(
            SecurityEvent.objects.filter(
                user=self.user, event="email_verified"
            ).count(),
            1,
        )

    def test_parallel_wrong_attempts_cannot_exceed_five(self):
        code, challenge = self.issue(number=111111)
        results = self.parallel(
            [
                lambda client: self.verify("999999", client=client).status_code
                for _ in range(6)
            ]
        )
        self.assertEqual(results, [400] * 6)
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 5)
        self.assertEqual(self.verify(code).status_code, 400)

    def test_simultaneous_resends_issue_only_one_new_code(self):
        _, challenge = self.issue()
        self.allow_resend(challenge)
        results = self.parallel(
            [
                lambda client: (
                    client.post(
                        PREFIX + "resend-verification/",
                        {"email": self.user.email},
                        format="json",
                    ).status_code
                ),
                lambda client: (
                    client.post(
                        PREFIX + "resend-verification/",
                        {"email": self.user.email},
                        format="json",
                    ).status_code
                ),
            ]
        )
        self.assertEqual(results, [200, 200])
        self.assertEqual(
            EmailVerificationChallenge.objects.filter(user=self.user).count(), 2
        )
        self.assertEqual(len(mail.outbox), 2)
