"""Append-only laboratory observations and patient-reported adherence."""

from datetime import timedelta

from accounts.permissions import IsVerifiedAccount
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response

from .health_tracking import (
    PERIOD_DAYS,
    adherence_data,
    lab_payload,
    lab_summary,
    latest_labs,
)
from .models import LabResult, MedicalReport, MedicationAdherenceLog
from .services import audit, own_patient, patient_access, role
from .views import DomainView, page


class StrictInput(serializers.Serializer):
    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "This field cannot be set here." for key in sorted(unknown)}
            )
        return attrs


class StrictInteger(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:
            raise serializers.ValidationError("Enter a whole number as an integer.")
        return super().to_internal_value(data)


class AdherenceInput(StrictInput):
    date = serializers.DateField()
    scheduled_doses = StrictInteger(min_value=1, max_value=10000)
    taken_doses = StrictInteger(min_value=0, max_value=10000)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        today = timezone.localdate()
        if not today - timedelta(days=PERIOD_DAYS - 1) <= attrs["date"] <= today:
            raise serializers.ValidationError(
                {"date": "Choose today or one of the previous 29 days."}
            )
        if attrs["taken_doses"] > attrs["scheduled_doses"]:
            raise serializers.ValidationError(
                {"taken_doses": "Taken doses cannot exceed scheduled doses."}
            )
        return attrs


class LabInput(StrictInput):
    name = serializers.CharField(max_length=120)
    value = serializers.DecimalField(max_digits=16, decimal_places=5)
    unit = serializers.CharField(max_length=40)
    reference_low = serializers.DecimalField(
        max_digits=16, decimal_places=5, allow_null=True, required=False
    )
    reference_high = serializers.DecimalField(
        max_digits=16, decimal_places=5, allow_null=True, required=False
    )
    measured_at = serializers.DateTimeField()
    report_id = serializers.UUIDField(allow_null=True, required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        low, high = attrs.get("reference_low"), attrs.get("reference_high")
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError(
                {
                    "reference_high": "Upper reference value must be at least the lower value."
                }
            )
        if attrs["measured_at"] > timezone.now():
            raise serializers.ValidationError(
                {"measured_at": "The measurement cannot be in the future."}
            )
        return attrs


class AdherenceView(DomainView):
    permission_classes = (IsVerifiedAccount,)

    def get(self, request):
        patient = own_patient(request.user)
        with patient_access(request.user, patient.id) as (patient, _, __):
            data = adherence_data(patient)
            audit(request, "adherence.read", patient)
            return Response(data)

    def put(self, request):
        patient = own_patient(request.user)
        serializer = AdherenceInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with patient_access(request.user, patient.id) as (patient, _, __):
            log, created = MedicationAdherenceLog.objects.update_or_create(
                patient=patient,
                date=data["date"],
                defaults={
                    **{key: data[key] for key in ("scheduled_doses", "taken_doses")},
                    "report": None,
                },
            )
            audit(
                request,
                "adherence.create" if created else "adherence.update",
                patient,
                log.id,
            )
            return Response(adherence_data(patient))


class LabsView(DomainView):
    permission_classes = (IsVerifiedAccount,)

    def resolve_patient_id(self, request, patient_id):
        if patient_id is None:
            return own_patient(request.user).id
        role(request.user, "doctor")
        return patient_id

    def get(self, request, patient_id=None):
        patient_id = self.resolve_patient_id(request, patient_id)
        with patient_access(request.user, patient_id) as (patient, _, __):
            query = (
                LabResult.objects.filter(patient=patient)
                .select_related("recorded_by")
                .order_by("-measured_at", "-created_at", "-id")
            )
            response = page(request, query, lab_payload)
            response.data["summary"] = lab_summary(latest_labs(patient))
            audit(request, "labs.read", patient)
            return response

    def post(self, request, patient_id=None):
        patient_id = self.resolve_patient_id(request, patient_id)
        serializer = LabInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        with patient_access(
            request.user, patient_id, write=request.user.role == "doctor"
        ) as (patient, _, __):
            report_id = data.pop("report_id", None)
            report = (
                get_object_or_404(MedicalReport, pk=report_id, patient=patient)
                if report_id
                else None
            )
            result = LabResult.objects.create(
                patient=patient, recorded_by=request.user, report=report, **data
            )
            audit(request, "labs.create", patient, result.id)
            return Response(lab_payload(result), status=201)
