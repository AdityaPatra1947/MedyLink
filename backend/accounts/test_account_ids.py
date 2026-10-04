from datetime import date, timedelta
from importlib import import_module
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .identifiers import ACCOUNT_ID_ALPHABET, ACCOUNT_ID_PREFIXES
from .models import AuthSession, User

PASSWORD = "Account-id-testing-passphrase-93742!"
PREFIX = "/api/v1/auth/"


class AccountIDTests(TestCase):
    def test_every_role_gets_a_unique_short_id_that_stays_stable(self):
        identifiers = []
        for role, prefix in ACCOUNT_ID_PREFIXES.items():
            user = User.objects.create_user(
                f"{role}@example.com", PASSWORD, name="Test Account", role=role
            )
            self.assertRegex(
                user.account_id, rf"^{prefix}-[{ACCOUNT_ID_ALPHABET}]{{6}}$"
            )
            identifiers.append(user.account_id)
            original = user.account_id
            user.name = "Updated Name"
            user.save(update_fields=["name"])
            user.refresh_from_db()
            self.assertEqual(user.account_id, original)
            self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(len(identifiers), len(set(identifiers)))
        admin = User.objects.create_superuser(
            "superuser@example.com", PASSWORD, name="Superuser"
        )
        self.assertTrue(admin.account_id.startswith("A-"))

    def test_collision_retries_inside_outer_transaction_without_losing_other_users(
        self,
    ):
        first = User.objects.create_user("first@example.com", PASSWORD, name="First")
        with patch(
            "accounts.models.generate_account_id",
            side_effect=[first.account_id, "P-XYZ234"],
        ) as generate:
            with transaction.atomic():
                second = User.objects.create_user(
                    "second@example.com", PASSWORD, name="Second"
                )
                self.assertEqual(User.objects.count(), 2)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(second.account_id, "P-XYZ234")
        first.refresh_from_db()
        self.assertNotEqual(first.account_id, second.account_id)

    def test_non_id_integrity_failure_is_not_retried(self):
        User.objects.create_user("same@example.com", PASSWORD, name="First")
        with patch(
            "accounts.models.generate_account_id", return_value="P-ABC234"
        ) as generate:
            with self.assertRaises(IntegrityError):
                User.objects.create_user(
                    "SAME@example.com", PASSWORD, name="Duplicate Email"
                )
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(User.objects.count(), 1)

    def test_repeated_collision_is_bounded_and_preserves_existing_account(self):
        first = User.objects.create_user("first@example.com", PASSWORD, name="First")
        with patch(
            "accounts.models.generate_account_id", return_value=first.account_id
        ) as generate:
            with self.assertRaises(IntegrityError):
                User.objects.create_user("second@example.com", PASSWORD, name="Second")
        self.assertEqual(generate.call_count, 10)
        self.assertEqual(User.objects.count(), 1)

    def test_registration_and_profile_cannot_set_or_change_account_id(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get(PREFIX + "csrf/").data["csrfToken"]
        client.credentials(HTTP_X_CSRFTOKEN=csrf)
        response = client.post(
            PREFIX + "register/",
            {
                "name": "New Patient",
                "email": "new@example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                "role": "patient",
                "consent": True,
                "date_of_birth": "1990-01-01",
                "account_id": "A-ABC234",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        user = User.objects.get(email="new@example.com")
        original = user.account_id
        self.assertTrue(original.startswith("P-"))
        self.assertNotEqual(original, "A-ABC234")
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
        signed_in = client.post(
            PREFIX + "login/",
            {"email": user.email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(signed_in.data["user"]["account_id"], original)
        changed = client.patch(
            "/api/v1/patients/me/",
            {"account_id": "P-ABC234", "address": "Updated address"},
            format="json",
        )
        self.assertEqual(changed.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.account_id, original)
        self.assertEqual(
            client.get(PREFIX + "me/").data["user"]["account_id"], original
        )
        self.assertFalse(User._meta.get_field("account_id").editable)
        with self.assertRaises(ValueError):
            User.objects.create_user(
                "chosen@example.com", PASSWORD, name="Chosen", account_id="P-ABC234"
            )

    def test_interactive_admin_bootstrap_generates_account_id(self):
        with (
            patch(
                "builtins.input",
                side_effect=["admin@example.com", "Test Administrator"],
            ),
            patch(
                "accounts.management.commands.bootstrap_admin.getpass",
                return_value=PASSWORD,
            ),
        ):
            call_command("bootstrap_admin", stdout=StringIO())
        admin = User.objects.get(email="admin@example.com")
        self.assertRegex(admin.account_id, rf"^A-[{ACCOUNT_ID_ALPHABET}]{{6}}$")
        self.assertTrue(admin.check_password(PASSWORD))
        self.assertTrue(admin.email_verified)


class AccountIDBackfillMigrationTests(TransactionTestCase):
    migrate_from = [("accounts", "0005_remove_authenticator")]
    migrate_to = [("accounts", "0006_user_account_id")]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_existing_accounts_are_backfilled_once_without_changing_credentials_or_relations(
        self,
    ):
        from clinic.models import Patient

        self.addCleanup(self.migrate, self.migrate_to)
        old_apps = self.migrate(self.migrate_from)
        OldUser = old_apps.get_model("accounts", "User")
        OldSession = old_apps.get_model("accounts", "AuthSession")
        expected = {}
        now = timezone.now()
        for role in ACCOUNT_ID_PREFIXES:
            password_hash = make_password(PASSWORD)
            user = OldUser.objects.create(
                email=f"old-{role}@example.com",
                name="Existing Account",
                role=role,
                password=password_hash,
                email_verified_at=now,
            )
            session = OldSession.objects.create(
                user=user, expires_at=now + timedelta(days=1), refresh_jti=f"old-{role}"
            )
            expected[user.id] = (role, password_hash, session.id)
            if role == "patient":
                patient = Patient.objects.create(
                    user_id=user.id,
                    date_of_birth=date(1990, 1, 1),
                    health_id="AT-LEGACY123456",
                    card_locator="existing-card-locator",
                )
        apps = self.migrate(self.migrate_to)
        ids = {}
        for user_id, (role, password_hash, session_id) in expected.items():
            user = User.objects.get(id=user_id)
            self.assertEqual(user.password, password_hash)
            self.assertEqual(user.role, role)
            self.assertEqual(user.email_verified_at, now)
            self.assertRegex(
                user.account_id,
                rf"^{ACCOUNT_ID_PREFIXES[role]}-[{ACCOUNT_ID_ALPHABET}]{{6}}$",
            )
            ids[user_id] = user.account_id
            session = AuthSession.objects.get(id=session_id)
            self.assertEqual(session.user_id, user_id)
            self.assertIsNone(session.revoked_at)
            self.assertEqual(session.refresh_jti, f"old-{role}")
        self.assertEqual(len(set(ids.values())), len(expected))
        patient.refresh_from_db()
        self.assertEqual(patient.health_id, "AT-LEGACY123456")
        self.assertEqual(patient.card_locator, "existing-card-locator")
        migration = import_module("accounts.migrations.0006_user_account_id")
        migration.populate_account_ids(apps, SimpleNamespace(connection=connection))
        self.assertEqual(dict(User.objects.values_list("id", "account_id")), ids)
