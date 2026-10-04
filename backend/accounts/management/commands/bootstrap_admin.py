from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from accounts.services import audit


class Command(BaseCommand):
    help = "Create an administrator interactively with a verified email and validated password."

    def handle(self, *args, **options):
        email = input("Administrator email: ").strip().lower()
        name = input("Administrator name: ").strip()
        password = getpass("Password: ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise CommandError("Passwords do not match.")
        if not name or len(name) > 150:
            raise CommandError("Provide a name of 1 to 150 characters.")
        user = User(
            email=email, name=name, role="admin", email_verified_at=timezone.now()
        )
        try:
            validate_email(email)
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from None
        try:
            with transaction.atomic():
                # This account signs in through the application with its email and password.
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    name=name,
                    role="admin",
                    email_verified_at=user.email_verified_at,
                )
                audit(user, "administrator_bootstrapped")
        except IntegrityError:
            raise CommandError("An account already uses that email address.") from None
        self.stdout.write(
            self.style.SUCCESS(
                "Administrator created. Sign in with the email and password."
            )
        )
