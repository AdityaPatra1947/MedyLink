"""A project rename must not duplicate demo identities or reset credentials."""

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .management.commands.create_demo_accounts import DEMO_EVENT, DEMO_USERS, LEGACY_DEMO_EMAILS
from .models import SecurityEvent, User


@override_settings(DEBUG=True)
class DemoAccountBrandingTests(TestCase):
    def setUp(self):
        local = settings.BASE_DIR.parent / ".local"
        local.mkdir(exist_ok=True)
        directory = TemporaryDirectory(prefix="demo-account-branding-", dir=local)
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "credentials.json"

    def run_command(self):
        call_command("create_demo_accounts", output=str(self.output), stdout=StringIO())

    def test_new_demo_accounts_use_current_brand_and_repeat_preserves_credentials(self):
        self.run_command()
        before = list(User.objects.order_by("email").values_list("id", "email", "password"))
        self.assertTrue(all(email.endswith("@medylink.test") for _, email, _ in before))
        self.run_command()
        self.assertEqual(list(User.objects.order_by("email").values_list("id", "email", "password")), before)

    def test_legacy_demo_accounts_are_reused_with_unchanged_login(self):
        credentials = {}
        for role, email, name in DEMO_USERS:
            legacy_email = LEGACY_DEMO_EMAILS[email]
            password = "Existing-demo-password!123"
            user = User.objects.create_user(legacy_email, password, name=name, role=role)
            SecurityEvent.objects.create(user=user, event=DEMO_EVENT)
            credentials[role] = {"email": legacy_email, "password": password}
        self.output.write_text(json.dumps(credentials), encoding="utf-8")
        before = list(User.objects.order_by("email").values_list("id", "email", "password"))
        self.run_command()
        self.assertEqual(list(User.objects.order_by("email").values_list("id", "email", "password")), before)
        User.objects.create_user(DEMO_USERS[0][1], "Another-password!123", name=DEMO_USERS[0][2], role="patient")
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertEqual(User.objects.count(), 3)
