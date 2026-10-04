import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import IntegrityError, connections, models, router, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from .identifiers import generate_account_id


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        if "account_id" in extra_fields:
            raise ValueError("Account IDs are generated automatically.")
        user = self.model(email=email.strip().lower(), **extra_fields)
        user.set_password(password)
        using = self._db or router.db_for_write(self.model)
        for attempt in range(10):
            user.account_id = generate_account_id(user.role)
            try:
                # A savepoint keeps a collision from breaking a signup transaction.
                with transaction.atomic(using=using):
                    user.save(using=using, force_insert=True)
                return user
            except IntegrityError as exc:
                if attempt == 9 or not self._is_account_id_collision(exc, using):
                    raise

    def _is_account_id_collision(self, error, using):
        cause = error.__cause__ or error
        constraint_name = getattr(getattr(cause, "diag", None), "constraint_name", None)
        if constraint_name:
            database = connections[using]
            with database.cursor() as cursor:
                constraint = database.introspection.get_constraints(
                    cursor, self.model._meta.db_table
                ).get(constraint_name, {})
            return bool(
                constraint.get("unique") and constraint.get("columns") == ["account_id"]
            )
        # SQLite names the exact failed column instead of a constraint.
        return str(cause) == (
            f"UNIQUE constraint failed: {self.model._meta.db_table}.account_id"
        )

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.update(role="admin", is_staff=True, is_superuser=True)
        extra_fields.setdefault("email_verified_at", timezone.now())
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        PATIENT = "patient", "Patient"
        DOCTOR = "doctor", "Doctor"
        PHARMACIST = "pharmacist", "Pharmacist"
        ADMIN = "admin", "Administrator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_id = models.CharField(max_length=9, unique=True, editable=False)
    email = models.EmailField(unique=True, max_length=254)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.PATIENT)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    storage_consent_at = models.DateTimeField(null=True, blank=True)
    privacy_version = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_email_case_unique"),
            models.CheckConstraint(
                condition=models.Q(
                    role__in=["patient", "doctor", "pharmacist", "admin"]
                ),
                name="accounts_valid_role",
            ),
        ]

    @property
    def email_verified(self):
        return self.email_verified_at is not None

    def __str__(self):
        return self.email


class AuthSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="auth_sessions"
    )
    refresh_jti = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.CharField(max_length=250, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "revoked_at"])]


class AccountToken(models.Model):
    class Purpose(models.TextChoices):
        VERIFY_EMAIL = "verify_email", "Email verification"
        RESET_PASSWORD = "reset_password", "Password reset"

    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="account_tokens"
    )
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class EmailVerificationChallenge(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="email_verification_challenges"
    )
    nonce = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    digest = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attempts__lte=5), name="email_verify_attempts_limit"
            ),
        ]


class SecurityEvent(models.Model):
    """Metadata-only audit trail; no tokens, email contents, or submitted credentials."""

    user = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="security_events"
    )
    event = models.CharField(max_length=60)
    outcome = models.CharField(max_length=12, default="success")
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
