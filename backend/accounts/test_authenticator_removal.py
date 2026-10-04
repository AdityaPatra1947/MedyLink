from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    AccountToken,
    AuthSession,
    EmailVerificationChallenge,
    SecurityEvent,
    User,
)
from .services import digest, email_code_digest

PREFIX = "/api/v1/auth/"
PASSWORD = "Migration-testing-passphrase-93742!"


class AuthenticatorRemovalMigrationTests(TransactionTestCase):
    migrate_from = [("accounts", "0004_emailverificationchallenge")]
    migrate_to = [("accounts", "0006_user_account_id")]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_previously_enrolled_accounts_keep_credentials_sessions_and_verification(
        self,
    ):
        self.addCleanup(self.migrate, self.migrate_to)
        old_apps = self.migrate(self.migrate_from)
        OldUser = old_apps.get_model("accounts", "User")
        OldSession = old_apps.get_model("accounts", "AuthSession")
        OldChallenge = old_apps.get_model("accounts", "MFAChallenge")
        OldRecovery = old_apps.get_model("accounts", "RecoveryCode")
        OldToken = old_apps.get_model("accounts", "AccountToken")
        OldEmailChallenge = old_apps.get_model("accounts", "EmailVerificationChallenge")
        OldAudit = old_apps.get_model("accounts", "SecurityEvent")
        now = timezone.now()
        migrated_accounts = []
        for role in User.Role.values:
            user = OldUser.objects.create(
                email=f"enrolled-{role}@example.com",
                name=f"Enrolled {role}",
                role=role,
                password=make_password(PASSWORD),
                email_verified_at=now,
                mfa_secret="legacy-encrypted-authenticator-secret",
                last_totp_counter=12345,
            )
            session = OldSession.objects.create(
                user=user,
                expires_at=now + timedelta(days=1),
                mfa_verified=True,
            )
            refresh = RefreshToken.for_user(
                User.objects.only("id", "password", "is_active").get(pk=user.pk)
            )
            refresh["sid"] = str(session.id)
            refresh["exp"] = int(session.expires_at.timestamp())
            session.refresh_jti = refresh["jti"]
            session.save(update_fields=["refresh_jti"])
            OldChallenge.objects.create(
                user=user,
                purpose="verify",
                digest=digest(f"legacy-challenge-{role}"),
                pending_secret="legacy-pending-secret",
                expires_at=now + timedelta(minutes=5),
            )
            OldRecovery.objects.create(
                user=user, password_hash=make_password("old-recovery-code")
            )
            reset = OldToken.objects.create(
                user=user,
                purpose="reset_password",
                digest=digest(f"reset-token-{role}"),
                expires_at=now + timedelta(minutes=30),
            )
            email_challenge = OldEmailChallenge(
                user=user, expires_at=now + timedelta(minutes=10)
            )
            email_challenge.digest = email_code_digest(
                user.id, email_challenge.nonce, "000007"
            )
            email_challenge.save()
            OldAudit.objects.create(user=user, event="mfa_enabled")
            migrated_accounts.append(
                (
                    user.id,
                    session.id,
                    reset.id,
                    email_challenge.id,
                    str(refresh),
                    str(refresh.access_token),
                )
            )

        self.migrate(self.migrate_to)

        tables = connection.introspection.table_names()
        self.assertNotIn("accounts_mfachallenge", tables)
        self.assertNotIn("accounts_recoverycode", tables)
        with connection.cursor() as cursor:
            user_columns = {
                field.name
                for field in connection.introspection.get_table_description(
                    cursor, "accounts_user"
                )
            }
            session_columns = {
                field.name
                for field in connection.introspection.get_table_description(
                    cursor, "accounts_authsession"
                )
            }
        self.assertNotIn("mfa_secret", user_columns)
        self.assertNotIn("last_totp_counter", user_columns)
        self.assertNotIn("mfa_verified", session_columns)

        for (
            user_id,
            session_id,
            reset_id,
            challenge_id,
            refresh,
            access,
        ) in migrated_accounts:
            with self.subTest(user_id=user_id):
                user = User.objects.get(id=user_id)
                self.assertTrue(user.check_password(PASSWORD))
                self.assertTrue(user.email_verified)
                self.assertIsNone(AuthSession.objects.get(id=session_id).revoked_at)
                self.assertEqual(
                    AccountToken.objects.get(id=reset_id).purpose, "reset_password"
                )
                self.assertIsNone(
                    EmailVerificationChallenge.objects.get(id=challenge_id).used_at
                )
                self.assertTrue(
                    SecurityEvent.objects.filter(
                        user=user, event="mfa_enabled"
                    ).exists()
                )
                client = APIClient(enforce_csrf_checks=True)
                csrf = client.get(PREFIX + "csrf/").data["csrfToken"]
                client.credentials(HTTP_X_CSRFTOKEN=csrf)
                client.cookies["access_token"] = access
                client.cookies["refresh_token"] = refresh
                self.assertEqual(client.get(PREFIX + "me/").status_code, 200)
                self.assertEqual(
                    client.post(PREFIX + "refresh/", {}, format="json").status_code, 200
                )
                signed_in = client.post(
                    PREFIX + "login/",
                    {"email": user.email, "password": PASSWORD},
                    format="json",
                )
                self.assertEqual(signed_in.status_code, 200)
                self.assertEqual(set(signed_in.data), {"user"})
                self.assertEqual(
                    set(signed_in.data["user"]),
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
