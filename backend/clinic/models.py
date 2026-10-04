import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


def health_id():
    # Existing IDs remain valid; only newly-created patients use the new prefix.
    return "ML-" + secrets.token_hex(6).upper()


def card_locator():
    return secrets.token_urlsafe(32)


class Base(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Patient(Base):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    health_id = models.CharField(
        max_length=32, unique=True, default=health_id, editable=False
    )
    card_locator = models.CharField(
        max_length=64, unique=True, default=card_locator, editable=False
    )
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("female", "Female"),
            ("male", "Male"),
            ("other", "Other"),
            ("prefer_not_to_say", "Prefer not to say"),
        ],
    )
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=500, blank=True)
    blood_group = models.CharField(max_length=8, default="unknown")
    emergency_contact = models.CharField(max_length=250, blank=True)
    allergy_status = models.CharField(max_length=15, default="unknown")
    photo_storage_name = models.CharField(max_length=100, blank=True)
    photo_content_type = models.CharField(max_length=40, blank=True)


class DoctorPatient(Base):
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="saved_patients",
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="saved_by_doctors"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "patient"], name="doctor_patient_unique"
            )
        ]
        indexes = [
            models.Index(
                fields=["doctor", "-created_at", "id"], name="doctor_saved_patient_idx"
            )
        ]


class ProviderApplication(Base):
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applications"
    )
    version = models.PositiveIntegerField()
    is_current = models.BooleanField(default=True)
    status = models.CharField(max_length=12, default="pending")
    registration_number = models.CharField(max_length=100)
    registering_body = models.CharField(max_length=150)
    specialty = models.CharField(max_length=150, blank=True)
    qualification = models.CharField(max_length=150, blank=True)
    clinic_name = models.CharField(max_length=180, blank=True)
    years_experience = models.PositiveSmallIntegerField(null=True, blank=True)
    opening_hours = models.CharField(max_length=300, blank=True)
    practice_address = models.CharField(max_length=500)
    shop_name = models.CharField(max_length=180, blank=True)
    shop_license = models.CharField(max_length=100, blank=True)
    shop_license_expires = models.DateField(null=True, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    reason = models.CharField(max_length=1000, blank=True)
    evidence_reviewed = models.CharField(max_length=1000, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "version"], name="provider_version_unique"
            ),
            models.UniqueConstraint(
                fields=["provider"],
                condition=Q(is_current=True),
                name="provider_current_unique",
            ),
            models.UniqueConstraint(
                fields=["registering_body", "registration_number"],
                condition=Q(is_current=True, status="approved"),
                name="approved_credential_unique",
            ),
            models.UniqueConstraint(
                fields=["registering_body", "shop_license"],
                condition=Q(is_current=True, status="approved") & ~Q(shop_license=""),
                name="approved_shop_license_unique",
            ),
        ]


class ProviderDocument(Base):
    application = models.ForeignKey(
        ProviderApplication, on_delete=models.PROTECT, related_name="documents"
    )
    name = models.CharField(max_length=180)
    storage_name = models.CharField(max_length=100, unique=True)
    content_type = models.CharField(max_length=40)
    kind = models.CharField(
        max_length=12,
        choices=[("credential", "Credential evidence"), ("photo", "Photo")],
        default="credential",
    )
    size_bytes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=15, default="quarantined")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT
    )
    reviewed_at = models.DateTimeField(null=True)
    review_reason = models.CharField(max_length=1000, blank=True)


class ProviderReview(Base):
    application = models.ForeignKey(
        ProviderApplication, on_delete=models.PROTECT, related_name="reviews"
    )
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decision = models.CharField(max_length=12)
    reason = models.CharField(max_length=1000)
    evidence_reviewed = models.CharField(max_length=1000, blank=True)
    valid_until = models.DateTimeField(null=True)


class AccessRequest(Base):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    application = models.ForeignKey(ProviderApplication, on_delete=models.PROTECT)
    scope = models.CharField(max_length=12)
    purpose = models.CharField(max_length=300)
    status = models.CharField(max_length=12, default="pending")


class MedicalRecord(Base):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    complaint = models.CharField(max_length=1000)
    diagnosis = models.CharField(max_length=1000, blank=True)
    notes = models.TextField(blank=True)
    vitals = models.JSONField(default=dict)
    correction_of = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    correction_reason = models.CharField(max_length=1000, blank=True)


class MedicalReport(Base):
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="reports"
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    record = models.ForeignKey(
        MedicalRecord,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports",
    )
    name = models.CharField(max_length=180)
    title = models.CharField(max_length=200, blank=True)
    storage_name = models.CharField(max_length=100, unique=True)
    content_type = models.CharField(max_length=40)
    size_bytes = models.PositiveIntegerField()
    extraction = models.JSONField(default=dict, blank=True, editable=False)


class ClinicalEntry(Base):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10)
    name = models.CharField(max_length=200)
    notes = models.CharField(max_length=1000, blank=True)
    source = models.CharField(max_length=20)
    resolved_at = models.DateTimeField(null=True)
    resolution_reason = models.CharField(max_length=1000, blank=True)


class Prescription(Base):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    application = models.ForeignKey(ProviderApplication, on_delete=models.PROTECT)
    record = models.ForeignKey(
        MedicalRecord, null=True, blank=True, on_delete=models.PROTECT
    )
    valid_until = models.DateTimeField()
    notes = models.CharField(max_length=2000, blank=True)
    cancelled_at = models.DateTimeField(null=True)
    cancellation_reason = models.CharField(max_length=1000, blank=True)


class PrescriptionItem(Base):
    prescription = models.ForeignKey(
        Prescription, on_delete=models.PROTECT, related_name="items"
    )
    medicine = models.CharField(max_length=200)
    dosage = models.CharField(max_length=250)
    instructions = models.CharField(max_length=1000, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit = models.CharField(max_length=40)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=Decimal("0")), name="prescribed_positive"
            )
        ]


class AccessGrant(Base):
    request = models.OneToOneField(AccessRequest, on_delete=models.PROTECT)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    application = models.ForeignKey(ProviderApplication, on_delete=models.PROTECT)
    scope = models.CharField(max_length=12)
    prescription = models.ForeignKey(Prescription, null=True, on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)


class DispenseEvent(Base):
    prescription = models.ForeignKey(
        Prescription, on_delete=models.PROTECT, related_name="dispensing"
    )
    pharmacist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    application = models.ForeignKey(ProviderApplication, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=100)
    payload_digest = models.CharField(max_length=64)
    patient_name = models.CharField(max_length=200)
    patient_health_id = models.CharField(max_length=32)
    pharmacist_name = models.CharField(max_length=200)
    shop_name = models.CharField(max_length=180)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pharmacist", "idempotency_key"],
                name="pharmacist_idempotency_unique",
            )
        ]


class DispenseItem(Base):
    event = models.ForeignKey(
        DispenseEvent, on_delete=models.PROTECT, related_name="items"
    )
    prescription_item = models.ForeignKey(
        PrescriptionItem, on_delete=models.PROTECT, related_name="dispenses"
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit = models.CharField(max_length=40)
    medicine = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=Decimal("0")), name="dispensed_positive"
            ),
            models.UniqueConstraint(
                fields=["event", "prescription_item"], name="dispense_item_unique"
            ),
        ]


class AuditEvent(Base):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT
    )
    patient = models.ForeignKey(Patient, null=True, on_delete=models.PROTECT)
    event = models.CharField(max_length=80)
    outcome = models.CharField(max_length=20, default="success")
    resource_id = models.CharField(max_length=100, blank=True)
    request_id = models.CharField(max_length=100, blank=True)


class MedicationAdherenceLog(Base):
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="adherence_logs"
    )
    date = models.DateField()
    scheduled_doses = models.PositiveIntegerField()
    taken_doses = models.PositiveIntegerField()
    report = models.ForeignKey(
        MedicalReport, null=True, blank=True, on_delete=models.PROTECT,
        related_name="adherence_logs",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "date"], name="patient_adherence_day_unique"
            ),
            models.CheckConstraint(
                condition=Q(scheduled_doses__gt=0), name="adherence_scheduled_positive"
            ),
            models.CheckConstraint(
                condition=Q(taken_doses__lte=models.F("scheduled_doses")),
                name="adherence_taken_within_schedule",
            ),
        ]
        indexes = [
            models.Index(fields=["patient", "-date"], name="patient_adherence_date_idx")
        ]


class LabResult(Base):
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="lab_results"
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    report = models.ForeignKey(
        MedicalReport,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lab_results",
    )
    name = models.CharField(max_length=120)
    value = models.DecimalField(max_digits=16, decimal_places=5)
    unit = models.CharField(max_length=40)
    reference_low = models.DecimalField(
        max_digits=16, decimal_places=5, null=True, blank=True
    )
    reference_high = models.DecimalField(
        max_digits=16, decimal_places=5, null=True, blank=True
    )
    measured_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(reference_low__isnull=True)
                | Q(reference_high__isnull=True)
                | Q(reference_low__lte=models.F("reference_high")),
                name="lab_reference_range_ordered",
            )
        ]
        indexes = [
            models.Index(
                fields=["patient", "-measured_at"], name="patient_lab_measured_idx"
            )
        ]
