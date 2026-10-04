import secrets
import uuid
from pathlib import Path

from accounts.permissions import IsVerifiedAccount
from accounts.serializers import user_payload
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import presentation as out
from .models import (
    AuditEvent,
    ClinicalEntry,
    DispenseEvent,
    DoctorPatient,
    MedicalRecord,
    MedicalReport,
    Patient,
    Prescription,
    PrescriptionItem,
    ProviderApplication,
    ProviderDocument,
    ProviderReview,
)
from .notifications import send_review_email
from .querysets import prescription_details
from .report_extraction import extract_report_observations
from .serializers import (
    ApplicationFilterInput,
    ApplicationInput,
    DispenseInput,
    DoctorProfileInput,
    EntryInput,
    PatientLookupInput,
    PrescriptionInput,
    ProfileInput,
    RecordInput,
    ReportInput,
    ReviewInput,
    validated,
)
from .services import (
    Conflict,
    approved,
    audit,
    dispense,
    own_patient,
    patient_access,
    revoke_provider,
    role,
)
from .uploads import (
    private_file_batch,
    save_document,
    save_private_upload,
    validate_upload,
)


def page(request, query, mapper):
    try:
        number = max(1, min(int(request.query_params.get("page", 1)), 10000))
    except (ValueError, TypeError):
        raise ValidationError({"page": "Enter a page number."})
    rows = list(query[(number - 1) * 50 : number * 50 + 1])
    return Response(
        {
            "results": [mapper(row) for row in rows[:50]],
            "next": number + 1 if len(rows) > 50 else None,
        }
    )


def required_reason(data):
    return validated(ReviewInput, data)["reason"]


class DomainView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        response["Referrer-Policy"] = "no-referrer"
        if response.status_code in (401, 403, 404):
            audit(request, "access.denied", outcome="denied")
        return response


class ProfileView(DomainView):
    def get(self, request):
        patient = own_patient(request.user)
        audit(request, "profile.read", patient)
        return Response(out.profile(patient))

    def patch(self, request):
        patient = own_patient(request.user)
        with patient_access(request.user, patient.id) as (patient, _, __):
            serializer = ProfileInput(patient, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            if (
                serializer.validated_data.get("allergy_status") == "none_known"
                and ClinicalEntry.objects.filter(
                    patient=patient, kind="allergy", resolved_at__isnull=True
                ).exists()
            ):
                raise ValidationError(
                    {
                        "allergy_status": "Active allergy entries must be resolved by their authors before marking no known allergies."
                    }
                )
            serializer.save()
            if "phone" in serializer.validated_data:
                get_user_model().objects.filter(pk=request.user.pk).update(
                    phone=patient.phone
                )
            audit(request, "profile.update", patient)
            return Response(out.profile(patient))


class CardView(DomainView):
    def get(self, request, pdf=False):
        patient = own_patient(request.user)
        if not patient.date_of_birth:
            raise ValidationError(
                "Complete your date of birth before generating a health card."
            )
        audit(request, "card.download" if pdf else "card.read", patient)
        return out.card_pdf(patient) if pdf else Response(out.card(patient))


class ReplaceCardView(DomainView):
    def post(self, request):
        patient = own_patient(request.user)
        with patient_access(request.user, patient.id) as (patient, _, __):
            if not patient.date_of_birth:
                raise ValidationError(
                    "Complete your date of birth before generating a health card."
                )
            patient.card_locator = secrets.token_urlsafe(32)
            patient.save(update_fields=["card_locator"])
            audit(request, "card.replace", patient)
            return Response(out.card(patient))


class ApplicationView(DomainView):
    def get(self, request):
        role(request.user, "doctor", "pharmacist")
        apps = list(
            ProviderApplication.objects.filter(provider=request.user)
            .select_related("provider")
            .prefetch_related("documents", "reviews__reviewer")
            .order_by("-version")[:50]
        )
        audit(request, "application.read")
        return Response(
            {
                "current": out.application(apps[0]) if apps else None,
                "history": [out.application(app) for app in apps],
            }
        )

    def post(self, request):
        role(request.user, "doctor", "pharmacist")
        data = validated(ApplicationInput, request.data, context={"user": request.user})
        with transaction.atomic():
            actor = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            previous = ProviderApplication.objects.filter(
                provider=actor, is_current=True
            ).first()
            if previous and previous.status == "suspended":
                raise PermissionDenied(
                    "A suspended provider must contact an administrator for review."
                )
            revoke_provider(actor)
            if previous:
                previous.is_current = False
                previous.save(update_fields=["is_current"])
            application = ProviderApplication.objects.create(
                provider=actor,
                version=(previous.version + 1 if previous else 1),
                **data,
            )
            audit(request, "application.submit", resource=application.id)
            return Response(out.application(application), status=201)


class UploadDocumentView(DomainView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        role(request.user, "doctor", "pharmacist")
        kind = request.data.get("kind", "credential")
        if kind not in ("credential", "photo"):
            raise ValidationError({"kind": "Choose credential or photo."})
        checked = validate_upload(request.FILES.get("file"), kind)
        with private_file_batch() as created_paths:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                app = get_object_or_404(
                    ProviderApplication,
                    provider=request.user,
                    is_current=True,
                    status="pending",
                )
                doc = save_document(app, checked, created_paths)
                audit(request, "document.upload", resource=doc.id)
            return Response(out.document(doc), status=201)


class DocumentDownloadView(DomainView):
    def get(self, request, pk):
        doc = get_object_or_404(
            ProviderDocument.objects.select_related("application"), pk=pk
        )
        if (
            request.user.role != "admin"
            and doc.application.provider_id != request.user.id
        ):
            raise NotFound()
        path = Path(settings.PRIVATE_MEDIA_ROOT) / doc.storage_name
        if not path.is_file():
            raise NotFound()
        audit(request, "document.download", resource=doc.id)
        response = FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename=doc.kind + path.suffix,
            content_type=doc.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ValidateDocumentView(DomainView):
    def post(self, request, pk):
        role(request.user, "admin")
        reason = required_reason(request.data)
        if not isinstance(request.data.get("safe"), bool):
            raise ValidationError({"safe": "A boolean review outcome is required."})
        with transaction.atomic():
            doc = get_object_or_404(ProviderDocument, pk=pk)
            get_user_model().objects.select_for_update().get(
                pk=doc.application.provider_id
            )
            doc = ProviderDocument.objects.select_for_update().get(pk=pk)
            if not doc.application.is_current or doc.application.status != "pending":
                raise Conflict(
                    "Only evidence for the current pending submission can be validated."
                )
            doc.status = "validated" if request.data["safe"] else "rejected"
            doc.reviewed_by = request.user
            doc.reviewed_at = timezone.now()
            doc.review_reason = reason
            doc.save(
                update_fields=["status", "reviewed_by", "reviewed_at", "review_reason"]
            )
            audit(request, "document.validate", resource=doc.id)
            return Response(out.document(doc))


class AdminApplicationsView(DomainView):
    def get(self, request, pk=None):
        role(request.user, "admin")
        audit(request, "application.review.read", resource=pk)
        query = ProviderApplication.objects.select_related("provider").prefetch_related(
            "documents", "reviews__reviewer"
        )
        if pk:
            app = get_object_or_404(query, pk=pk)
            result = out.application(app)
            result["history"] = [
                out.application(previous)
                for previous in query.filter(provider_id=app.provider_id)
                .exclude(pk=app.pk)
                .order_by("-version")[:50]
            ]
            return Response(result)
        filters = validated(ApplicationFilterInput, request.query_params)
        query = query.filter(is_current=True)
        if filters.get("role"):
            query = query.filter(provider__role=filters["role"])
        expired = Q(status="approved") & (
            Q(valid_until__lte=timezone.now())
            | Q(valid_until__isnull=True)
            | (
                Q(provider__role="pharmacist")
                & (
                    Q(shop_license_expires__lt=timezone.localdate())
                    | Q(shop_license_expires__isnull=True)
                )
            )
        )
        if filters.get("status") == "expired":
            query = query.filter(expired)
        elif filters.get("status"):
            query = query.filter(status=filters["status"])
            if filters["status"] == "approved":
                query = query.exclude(expired)
        if filters.get("search"):
            value = filters["search"]
            query = query.filter(
                Q(provider__name__icontains=value)
                | Q(provider__email__icontains=value)
                | Q(registration_number__icontains=value)
                | Q(registering_body__icontains=value)
                | Q(shop_name__icontains=value)
                | Q(shop_license__icontains=value)
            )
        return page(
            request,
            query.order_by("-created_at", "id"),
            out.application,
        )


class ReviewApplicationView(DomainView):
    def post(self, request, pk, decision):
        role(request.user, "admin")
        data = validated(ReviewInput, request.data)
        application = get_object_or_404(ProviderApplication, pk=pk)
        try:
            with transaction.atomic():
                actor = (
                    get_user_model()
                    .objects.select_for_update()
                    .get(pk=application.provider_id)
                )
                app = ProviderApplication.objects.select_for_update().get(pk=pk)
                if not app.is_current or app.status not in (
                    "pending",
                    "suspended",
                    "approved",
                ):
                    raise Conflict("This submission is not available for review.")
                if decision == "approve":
                    if not actor.is_active or not actor.email_verified:
                        raise ValidationError(
                            "The provider must verify their email and have an active account before approval."
                        )
                    if (
                        not data.get("valid_until")
                        or data["valid_until"] <= timezone.now()
                        or not data.get("evidence_reviewed")
                    ):
                        raise ValidationError(
                            "Approval requires future validity and evidence reviewed."
                        )
                    if (
                        not app.documents.filter(
                            kind="credential", status="validated"
                        ).exists()
                        or app.documents.filter(kind="credential")
                        .exclude(status="validated")
                        .exists()
                    ):
                        raise ValidationError(
                            "Validate all submitted evidence before approval."
                        )
                    if actor.role == "pharmacist" and (
                        not app.shop_license_expires
                        or app.shop_license_expires < data["valid_until"].date()
                    ):
                        raise ValidationError(
                            "Approval cannot exceed shop license validity."
                        )
                revoke_provider(actor)
                # New approval invalidates older grants even for the same submission.
                app.status = "approved" if decision == "approve" else "rejected"
                app.reason = data["reason"]
                app.evidence_reviewed = data.get("evidence_reviewed", "")
                app.valid_until = (
                    data.get("valid_until") if decision == "approve" else None
                )
                app.reviewer = request.user
                app.reviewed_at = timezone.now()
                app.save()
                ProviderReview.objects.create(
                    application=app,
                    reviewer=request.user,
                    decision=decision,
                    reason=app.reason,
                    evidence_reviewed=app.evidence_reviewed,
                    valid_until=app.valid_until,
                )
                audit(request, "application." + decision, resource=app.id)
                transaction.on_commit(
                    lambda: send_review_email(
                        email=actor.email,
                        name=actor.name,
                        decision=app.status,
                        reason=app.reason,
                        role=actor.role,
                        application_id=str(app.id),
                    )
                )
                return Response(out.application(app))
        except IntegrityError:
            raise Conflict(
                "This credential identity is already approved. Resolve the duplicate in manual review."
            )


class SuspendProviderView(DomainView):
    def post(self, request, pk):
        role(request.user, "admin")
        reason = required_reason(request.data)
        with transaction.atomic():
            provider = get_object_or_404(
                get_user_model().objects.select_for_update(),
                pk=pk,
                role__in=["doctor", "pharmacist"],
            )
            app = get_object_or_404(
                ProviderApplication, provider=provider, is_current=True
            )
            revoke_provider(provider)
            app.status = "suspended"
            app.reason = reason
            app.reviewer = request.user
            app.reviewed_at = timezone.now()
            app.save(update_fields=["status", "reason", "reviewer", "reviewed_at"])
            ProviderReview.objects.create(
                application=app,
                reviewer=request.user,
                decision="suspend",
                reason=reason,
            )
            audit(request, "provider.suspend", resource=pk)
            transaction.on_commit(
                lambda: send_review_email(
                    email=provider.email,
                    name=provider.name,
                    decision=app.status,
                    reason=reason,
                    role=provider.role,
                    application_id=str(app.id),
                )
            )
            return Response(out.application(app))


class PatientLookupView(DomainView):
    def post(self, request):
        data = validated(PatientLookupInput, request.data)
        with transaction.atomic():
            actor = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if not actor.is_active:
                raise PermissionDenied("Account disabled.")
            approved(actor)
            patient = (
                Patient.objects.select_for_update(of=("self",))
                .select_related("user")
                .filter(
                    Q(health_id=data["identifier"])
                    | Q(card_locator=data["identifier"])
                    | Q(user__account_id=data["identifier"].upper()),
                    user__is_active=True,
                )
                .first()
            )
            if not patient:
                raise NotFound("No patient was found for this identifier.")
            audit(request, "patient.lookup", patient)
            return Response(
                {
                    "patient_id": str(patient.id),
                    "patient": out.patient_identity(patient),
                }
            )


class DoctorPatientsView(DomainView):
    def get(self, request):
        role(request.user, "doctor")
        with transaction.atomic():
            actor = get_user_model().objects.select_for_update().get(pk=request.user.id)
            approved(actor)
            saved = (
                DoctorPatient.objects.filter(
                    doctor=actor, patient__user__is_active=True
                )
                .select_related("patient__user")
                .order_by("-created_at", "id")
            )
            audit(request, "doctor.patients.read")
            return page(request, saved, lambda row: out.profile(row.patient))


class AddDoctorPatientView(DomainView):
    def post(self, request, patient_id):
        role(request.user, "doctor")
        with patient_access(request.user, patient_id, write=True) as (patient, _, __):
            if not patient.user.is_active:
                raise NotFound("This patient account is unavailable.")
            saved, created = DoctorPatient.objects.get_or_create(
                doctor=request.user, patient=patient
            )
            if created:
                audit(request, "doctor.patient.add", patient, saved.id)
            return Response(
                {
                    "patient": out.profile(patient),
                    "is_my_patient": True,
                    "created": created,
                },
                status=201 if created else 200,
            )


class DoctorProfileView(DomainView):
    permission_classes = [IsVerifiedAccount]

    def payload(self, actor):
        application = (
            ProviderApplication.objects.filter(provider=actor, is_current=True)
            .select_related("provider")
            .prefetch_related("documents", "reviews__reviewer")
            .first()
        )
        return {
            "user": user_payload(actor),
            "application": out.application(application) if application else None,
        }

    def get(self, request):
        role(request.user, "doctor")
        audit(request, "doctor.profile.read")
        return Response(self.payload(request.user))

    def patch(self, request):
        role(request.user, "doctor")
        data = validated(DoctorProfileInput, request.data)
        with transaction.atomic():
            actor = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            role(actor, "doctor")
            if not actor.is_active or not actor.email_verified:
                raise PermissionDenied("A verified, active account is required.")
            for key, value in data.items():
                setattr(actor, key, value)
            actor.save(update_fields=list(data))
            audit(request, "doctor.profile.update", resource=actor.pk)
            return Response(self.payload(actor))


class RecordsView(DomainView):
    def get(self, request, patient_id=None):
        patient_id = patient_id or own_patient(request.user).id
        with patient_access(request.user, patient_id) as (patient, _, __):
            audit(request, "records.read", patient)
            return page(
                request,
                MedicalRecord.objects.filter(patient=patient)
                .select_related("doctor")
                .order_by("-created_at", "-id"),
                out.record,
            )

    def post(self, request, patient_id):
        data = validated(RecordInput, request.data)
        if data.get("correction_reason"):
            raise ValidationError(
                "Use the correction endpoint to correct an existing record."
            )
        with patient_access(request.user, patient_id, write=True) as (patient, _, __):
            record = MedicalRecord.objects.create(
                patient=patient, doctor=request.user, **data
            )
            audit(request, "record.create", patient, record.id)
            return Response(out.record(record), status=201)


class CorrectionView(DomainView):
    def post(self, request, pk):
        original = get_object_or_404(MedicalRecord, pk=pk)
        data = validated(RecordInput, request.data)
        if not data.get("correction_reason"):
            raise ValidationError({"correction_reason": "Explain the correction."})
        with patient_access(request.user, original.patient_id, write=True) as (
            patient,
            _,
            __,
        ):
            if original.doctor_id != request.user.id:
                raise PermissionDenied(
                    "Only the author can add a correction to this record."
                )
            record = MedicalRecord.objects.create(
                patient=patient, doctor=request.user, correction_of=original, **data
            )
            audit(request, "record.correct", patient, record.id)
            return Response(out.record(record), status=201)


class EntriesView(DomainView):
    def get(self, request, patient_id, kind):
        with patient_access(request.user, patient_id) as (patient, _, __):
            audit(request, kind + ".read", patient)
            return page(
                request,
                ClinicalEntry.objects.filter(patient=patient, kind=kind).order_by(
                    "-created_at"
                ),
                out.entry,
            )

    def post(self, request, patient_id, kind):
        data = validated(EntryInput, request.data)
        with patient_access(request.user, patient_id) as (patient, _, __):
            entry = ClinicalEntry.objects.create(
                patient=patient,
                author=request.user,
                kind=kind,
                source="patient_reported"
                if request.user.role == "patient"
                else "clinician_recorded",
                **data,
            )
            if kind == "allergy":
                patient.allergy_status = "reported"
                patient.save(update_fields=["allergy_status"])
            audit(request, kind + ".create", patient, entry.id)
            return Response(out.entry(entry), status=201)


class ResolveEntryView(DomainView):
    def post(self, request, patient_id, kind, pk):
        reason = required_reason(request.data)
        with patient_access(request.user, patient_id) as (patient, _, __):
            entry = get_object_or_404(ClinicalEntry, pk=pk, patient=patient, kind=kind)
            if entry.author_id != request.user.id:
                raise PermissionDenied("Only the author may resolve their own entry.")
            if entry.resolved_at:
                raise Conflict("This entry was already resolved.")
            entry.resolved_at = timezone.now()
            entry.resolution_reason = reason
            entry.save(update_fields=["resolved_at", "resolution_reason"])
            audit(request, kind + ".resolve", patient, entry.id)
            return Response(out.entry(entry))


class ClinicalSummaryView(DomainView):
    def get(self, request, patient_id):
        with patient_access(request.user, patient_id) as (patient, _, __):
            audit(request, "clinical_summary.read", patient)
            return Response(
                dict(
                    patient=out.profile(patient),
                    is_my_patient=(
                        request.user.role == "doctor"
                        and DoctorPatient.objects.filter(
                            doctor=request.user, patient=patient
                        ).exists()
                    ),
                    allergies=[
                        out.entry(e)
                        for e in ClinicalEntry.objects.filter(
                            patient=patient, kind="allergy"
                        ).order_by("-created_at")[:50]
                    ],
                    conditions=[
                        out.entry(e)
                        for e in ClinicalEntry.objects.filter(
                            patient=patient, kind="condition"
                        ).order_by("-created_at")[:50]
                    ],
                    records=[
                        out.record(r)
                        for r in MedicalRecord.objects.filter(patient=patient).select_related("doctor").order_by(
                            "-created_at"
                        )[:50]
                    ],
                    prescriptions=[
                        out.prescription(rx)
                        for rx in prescription_details(Prescription.objects.filter(patient=patient)).order_by("-created_at")[:50]
                    ],
                )
            )


class PrescriptionsView(DomainView):
    def get(self, request, patient_id=None):
        patient_id = patient_id or own_patient(request.user).id
        with patient_access(request.user, patient_id, pharmacy=True) as (
            patient,
            _,
            __,
        ):
            audit(request, "prescriptions.read", patient)
            return page(
                request,
                prescription_details(Prescription.objects.filter(patient=patient)).order_by("-created_at"),
                lambda rx: out.prescription(
                    rx, clinical=request.user.role != "pharmacist"
                ),
            )

    def post(self, request, patient_id):
        data = validated(PrescriptionInput, request.data)
        with patient_access(request.user, patient_id, write=True) as (patient, app, _):
            record_id = data.pop("record_id", None)
            if record_id:
                get_object_or_404(
                    MedicalRecord, pk=record_id, patient=patient, doctor=request.user
                )
            items = data.pop("items")
            prescription = Prescription.objects.create(
                patient=patient,
                doctor=request.user,
                application=app,
                record_id=record_id,
                **data,
            )
            PrescriptionItem.objects.bulk_create(
                [PrescriptionItem(prescription=prescription, **item) for item in items]
            )
            audit(request, "prescription.create", patient, prescription.id)
            return Response(out.prescription(prescription), status=201)


class PrescriptionView(DomainView):
    def get(self, request, pk, pdf=False):
        prescription = get_object_or_404(Prescription, pk=pk)
        with patient_access(
            request.user, prescription.patient_id, prescription_id=pk
        ) as (patient, _, __):
            prescription = Prescription.objects.select_for_update().get(pk=pk)
            audit(
                request,
                "prescription.download" if pdf else "prescription.read",
                patient,
                pk,
            )
            data = out.prescription(
                prescription, clinical=request.user.role != "pharmacist"
            )
            return out.prescription_pdf(data) if pdf else Response(data)


class CancelPrescriptionView(DomainView):
    def post(self, request, pk):
        prescription = get_object_or_404(Prescription, pk=pk)
        reason = required_reason(request.data)
        with patient_access(request.user, prescription.patient_id, write=True) as (
            patient,
            _,
            __,
        ):
            prescription = Prescription.objects.select_for_update().get(pk=pk)
            if prescription.doctor_id != request.user.id:
                raise PermissionDenied(
                    "Only the issuing doctor may cancel a prescription."
                )
            if not prescription.cancelled_at:
                prescription.cancelled_at = timezone.now()
                prescription.cancellation_reason = reason
                prescription.save(update_fields=["cancelled_at", "cancellation_reason"])
                audit(request, "prescription.cancel", patient, pk)
            return Response(out.prescription(prescription))


class SharedPrescriptionsView(DomainView):
    """Legacy URL exposes only this pharmacy's previously dispensed prescriptions."""

    def get(self, request):
        role(request.user, "pharmacist")
        with transaction.atomic():
            actor = get_user_model().objects.select_for_update().get(pk=request.user.id)
            approved(actor)
            ids = DispenseEvent.objects.filter(pharmacist=actor).values(
                "prescription_id"
            )
            audit(request, "pharmacy.prescriptions.read")
            return page(
                request,
                Prescription.objects.filter(pk__in=ids).order_by("-created_at"),
                lambda rx: out.prescription(rx, clinical=False),
            )


class DispenseView(DomainView):
    def post(self, request, pk):
        data = validated(DispenseInput, request.data)
        prescription = get_object_or_404(Prescription, pk=pk)
        event, created = dispense(
            request, prescription, data, request.headers.get("Idempotency-Key")
        )
        return Response(out.dispense_event(event), status=201 if created else 200)


class DispensingHistoryView(DomainView):
    def get(self, request):
        role(request.user, "patient", "pharmacist")
        if request.user.role == "patient":
            patient = own_patient(request.user)
            query = DispenseEvent.objects.filter(prescription__patient=patient)
        else:
            patient = None
            query = DispenseEvent.objects.filter(pharmacist=request.user)
        audit(request, "dispensing_history.read", patient)
        return page(request, query.order_by("-created_at"), out.dispense_event)


class AuditView(DomainView):
    def get(self, request, admin=False):
        if admin:
            from accounts.models import SecurityEvent
            from django.db.models import CharField, Value
            from django.db.models.functions import Cast, Coalesce

            role(request.user, "admin")
            fields = (
                "event_id",
                "actor_name",
                "event",
                "outcome",
                "created_at",
                "request_id",
            )
            clinical = (
                AuditEvent.objects.order_by()
                .annotate(
                    event_id=Cast("id", output_field=CharField()),
                    actor_name=Coalesce("actor__name", Value("System")),
                )
                .values(*fields)
            )
            security = (
                SecurityEvent.objects.order_by()
                .annotate(
                    event_id=Cast("id", output_field=CharField()),
                    actor_name=Coalesce("user__name", Value("System")),
                )
                .values(*fields)
            )
            # Union only the allowed metadata columns; neither clinical resources
            # nor security-event metadata (including recovery review notes) is selected.
            query = clinical.union(security, all=True).order_by(
                "-created_at", "event_id"
            )
            return page(
                request,
                query,
                lambda row: {
                    "id": str(uuid.UUID(row["event_id"]))
                    if len(row["event_id"]) in (32, 36)
                    else row["event_id"],
                    "actor_name": row["actor_name"],
                    "event": row["event"],
                    "outcome": row["outcome"],
                    "created_at": row["created_at"],
                    "request_id": row["request_id"],
                },
            )
        else:
            query = AuditEvent.objects.filter(patient=own_patient(request.user))
        return page(request, query.order_by("-created_at"), out.audit_event)


class PatientPhotoView(DomainView):
    parser_classes = [MultiPartParser]

    def post(self, request, patient_id=None):
        patient = own_patient(request.user)
        if patient_id is not None and patient_id != patient.id:
            raise PermissionDenied("You can update only your own photo.")
        checked = validate_upload(request.FILES.get("file"), "photo")
        with private_file_batch() as paths:
            with patient_access(request.user, patient.id) as (patient, _, __):
                previous = patient.photo_storage_name
                patient.photo_storage_name = save_private_upload(checked, paths)
                patient.photo_content_type = checked.content_type
                patient.save(update_fields=["photo_storage_name", "photo_content_type"])
                if previous:
                    transaction.on_commit(lambda: _remove_old_photo(previous))
                audit(request, "patient.photo.upload", patient)
            return Response(out.profile(patient), status=201)

    def get(self, request, patient_id=None):
        patient_id = patient_id or own_patient(request.user).id
        with patient_access(request.user, patient_id, pharmacy=True) as (
            patient,
            _,
            __,
        ):
            if not patient.photo_storage_name:
                raise NotFound()
            path = Path(settings.PRIVATE_MEDIA_ROOT) / patient.photo_storage_name
            if not path.is_file():
                raise NotFound()
            audit(request, "patient.photo.read", patient)
            response = FileResponse(
                path.open("rb"), content_type=patient.photo_content_type
            )
            response["X-Content-Type-Options"] = "nosniff"
            return response


def _remove_old_photo(storage_name):
    # A cleanup failure must not undo a successfully committed photo replacement.
    try:
        (Path(settings.PRIVATE_MEDIA_ROOT) / storage_name).unlink(missing_ok=True)
    except OSError:
        import logging

        logging.getLogger(__name__).warning("Old patient photo cleanup failed.")


class ReportsView(DomainView):
    parser_classes = [MultiPartParser]

    def get(self, request, patient_id=None):
        patient_id = patient_id or own_patient(request.user).id
        with patient_access(request.user, patient_id) as (patient, _, __):
            audit(request, "reports.read", patient)
            return page(
                request,
                MedicalReport.objects.filter(patient=patient)
                .select_related("uploaded_by")
                .order_by("-created_at", "-id"),
                out.report,
            )

    def post(self, request, patient_id=None):
        patient_id = patient_id or own_patient(request.user).id
        data = validated(ReportInput, request.data)
        checked = validate_upload(request.FILES.get("file"), "report")
        with private_file_batch() as paths:
            with patient_access(request.user, patient_id) as (patient, _, __):
                record_id = data.get("record_id")
                if record_id:
                    records = MedicalRecord.objects.filter(patient=patient)
                    if request.user.role == "doctor":
                        records = records.filter(doctor=request.user)
                    get_object_or_404(records, pk=record_id)
                report = MedicalReport.objects.create(
                    patient=patient,
                    uploaded_by=request.user,
                    record_id=record_id,
                    title=data["title"],
                    name=Path(checked.upload.name).name[:180],
                    storage_name=save_private_upload(checked, paths),
                    content_type=checked.content_type,
                    size_bytes=checked.upload.size,
                )
                extract_report_observations(report, checked.upload)
                audit(request, "report.upload", patient, report.id)
            return Response(out.report(report), status=201)


class ReportDownloadView(DomainView):
    def get(self, request, pk, inline=False):
        report = get_object_or_404(MedicalReport, pk=pk)
        with patient_access(request.user, report.patient_id) as (patient, _, __):
            path = Path(settings.PRIVATE_MEDIA_ROOT) / report.storage_name
            if not path.is_file():
                raise NotFound()
            audit(request, "report.view" if inline else "report.download", patient, report.id)
            response = FileResponse(
                path.open("rb"),
                as_attachment=not inline,
                filename=Path(report.name).name or "report" + path.suffix,
                content_type=report.content_type,
            )
            response["X-Content-Type-Options"] = "nosniff"
            return response


class VisitsView(DomainView):
    def get(self, request):
        patient = own_patient(request.user)
        with patient_access(request.user, patient.id) as (patient, _, __):
            audit(request, "visits.read", patient)
            records = (
                MedicalRecord.objects.filter(patient=patient)
                .select_related("doctor")
                .prefetch_related(
                    "reports__uploaded_by",
                    Prefetch("doctor__applications", to_attr="visit_applications", queryset=ProviderApplication.objects.order_by("-version")),
                    Prefetch("prescription_set", queryset=prescription_details(Prescription.objects.all())),
                )
                .order_by("-created_at", "-id")
            )
            return page(request, records, out.visit)
