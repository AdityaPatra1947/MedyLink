import hashlib
import json
from contextlib import contextmanager
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import (
    APIException,
    NotFound,
    PermissionDenied,
    ValidationError,
)

from .models import (
    AccessGrant,
    AccessRequest,
    AuditEvent,
    DispenseEvent,
    DispenseItem,
    Patient,
    Prescription,
    PrescriptionItem,
    ProviderApplication,
)


class Conflict(APIException):
    status_code = 409
    default_code = "state_conflict"
    default_detail = "The requested operation conflicts with current state."


def role(user, *roles):
    if user.role not in roles:
        raise PermissionDenied("This action is unavailable for your account role.")


def audit(request, event, patient=None, resource=None, outcome="success"):
    AuditEvent.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        patient=patient,
        event=event,
        outcome=outcome,
        resource_id=str(resource or ""),
        request_id=str(getattr(request, "request_id", ""))[:100],
    )


def own_patient(user):
    role(user, "patient")
    for _ in range(5):
        try:
            with transaction.atomic():
                patient, _ = Patient.objects.get_or_create(user=user)
                return patient
        except IntegrityError:
            existing = Patient.objects.filter(user=user).first()
            if existing:
                return existing
    raise Conflict("Unable to allocate health identity. Retry.")


def approved(user):
    role(user, "doctor", "pharmacist")
    if not user.is_active or not user.email_verified:
        raise PermissionDenied("A verified, active account is required.")
    app = ProviderApplication.objects.filter(
        provider=user,
        is_current=True,
        status="approved",
        valid_until__gt=timezone.now(),
    ).first()
    if not app or (
        user.role == "pharmacist"
        and (
            not app.shop_license_expires
            or app.shop_license_expires < timezone.localdate()
        )
    ):
        raise PermissionDenied("Current professional approval is required.")
    return app


@contextmanager
def patient_access(
    user, patient_id, *, write=False, prescription_id=None, pharmacy=False
):
    """Serialize provider status -> patient -> prescription for clinical transactions.

    Legacy patient grants are retained as historical data, but no longer authorize
    or limit access. Pharmacy access is explicitly limited to prescription/photo views.
    """
    with transaction.atomic():
        actor = get_user_model().objects.select_for_update().get(pk=user.pk)
        if not actor.is_active:
            raise PermissionDenied("Account disabled.")
        role(actor, "patient", "doctor", "pharmacist")
        app = approved(actor) if actor.role in ("doctor", "pharmacist") else None
        if actor.role == "pharmacist" and (write or not (prescription_id or pharmacy)):
            raise PermissionDenied(
                "Pharmacy access is restricted to patient identification and prescriptions."
            )
        patient = (
            Patient.objects.select_for_update(of=("self",))
            .filter(pk=patient_id)
            .select_related("user")
            .first()
        )
        if patient is None:
            raise NotFound()
        if actor.role == "patient" and (patient.user_id != actor.pk or write):
            raise PermissionDenied("This action requires an authorized doctor.")
        yield patient, app, None


def revoke_provider(user):
    # Caller holds provider user lock. Lock affected patients before grants.
    patient_ids = AccessGrant.objects.filter(
        provider=user, revoked_at__isnull=True
    ).values_list("patient_id", flat=True)
    list(Patient.objects.select_for_update().filter(id__in=patient_ids).order_by("id"))
    AccessGrant.objects.filter(provider=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    AccessRequest.objects.filter(provider=user, status="pending").update(
        status="revoked"
    )


def totals(item):
    return item.dispenses.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


def dispense(request, prescription, data, key):
    role(request.user, "pharmacist")
    if not key or len(key) > 100:
        raise ValidationError(
            {"Idempotency-Key": "Supply a unique key of at most 100 characters."}
        )
    canonical = {
        "prescription": str(prescription.id),
        "items": sorted(
            [
                {
                    "id": str(i["prescription_item_id"]),
                    "quantity": str(i["quantity"]),
                    "unit": i["unit"],
                }
                for i in data["items"]
            ],
            key=lambda i: i["id"],
        ),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    with patient_access(
        request.user, prescription.patient_id, prescription_id=prescription.id
    ) as (patient, app, grant):
        locked = Prescription.objects.select_for_update().get(pk=prescription.id)
        previous = DispenseEvent.objects.filter(
            pharmacist=request.user, idempotency_key=key
        ).first()
        if previous:
            if previous.payload_digest != digest:
                raise Conflict(
                    "This idempotency key was already used for another payload."
                )
            audit(request, "dispense.replay", patient, previous.id)
            return previous, False
        if locked.cancelled_at or locked.valid_until <= timezone.now():
            raise Conflict("This prescription is cancelled or expired.")
        items = {
            item.id: item
            for item in PrescriptionItem.objects.select_for_update()
            .filter(prescription=locked)
            .order_by("id")
        }
        for row in data["items"]:
            item = items.get(row["prescription_item_id"])
            if item is None:
                raise ValidationError("Every item must belong to this prescription.")
            if row["unit"] != item.unit:
                raise ValidationError("Dispense using the exact prescribed unit.")
            if row["quantity"] > item.quantity - totals(item):
                raise Conflict("Quantity exceeds the remaining prescribed balance.")
        event = DispenseEvent.objects.create(
            prescription=locked,
            pharmacist=request.user,
            application=app,
            idempotency_key=key,
            payload_digest=digest,
            patient_name=patient.user.name,
            patient_health_id=patient.health_id,
            pharmacist_name=request.user.name,
            shop_name=app.shop_name,
        )
        DispenseItem.objects.bulk_create(
            [
                DispenseItem(
                    event=event,
                    prescription_item=items[row["prescription_item_id"]],
                    quantity=row["quantity"],
                    unit=row["unit"],
                    medicine=items[row["prescription_item_id"]].medicine,
                )
                for row in data["items"]
            ]
        )
        audit(request, "prescription.dispense", patient, event.id)
        return event, True
