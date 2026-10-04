from datetime import date
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import ClinicalEntry, MedicalRecord, Patient, ProviderApplication


class ProfileInput(serializers.ModelSerializer):
    blood_group = serializers.ChoiceField(
        choices=["unknown", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
        required=False,
    )
    allergy_status = serializers.ChoiceField(
        choices=["unknown", "none_known", "reported"], required=False
    )

    class Meta:
        model = Patient
        fields = [
            "date_of_birth",
            "gender",
            "phone",
            "address",
            "blood_group",
            "emergency_contact",
            "allergy_status",
        ]

    def validate_date_of_birth(self, value):
        if value is None:
            raise serializers.ValidationError("Date of birth is required.")
        today = timezone.localdate()
        age = (
            today.year
            - value.year
            - ((today.month, today.day) < (value.month, value.day))
        )
        if age < 18 or value < date(1900, 1, 1):
            raise serializers.ValidationError(
                "This release supports adults aged 18 or older. Enter a valid date."
            )
        return value


class ApplicationInput(serializers.ModelSerializer):
    years_experience = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=80
    )

    class Meta:
        model = ProviderApplication
        fields = [
            "registration_number",
            "registering_body",
            "specialty",
            "qualification",
            "clinic_name",
            "years_experience",
            "opening_hours",
            "practice_address",
            "shop_name",
            "shop_license",
            "shop_license_expires",
            "contact_phone",
        ]

    def validate(self, data):
        for key in ["registration_number", "registering_body", "shop_license"]:
            if key in data:
                data[key] = data[key].strip().upper()
        if self.context["user"].role == "pharmacist":
            for key in ["shop_name", "shop_license", "shop_license_expires"]:
                if not data.get(key):
                    raise serializers.ValidationError(
                        {key: "Required for a pharmacy application."}
                    )
            if data["shop_license_expires"] < timezone.localdate():
                raise serializers.ValidationError(
                    {"shop_license_expires": "License has expired."}
                )
        else:
            for key in ["specialty", "qualification"]:
                if not data.get(key):
                    raise serializers.ValidationError(
                        {key: "Required for a doctor application."}
                    )
        return data


class RecordInput(serializers.ModelSerializer):
    notes = serializers.CharField(max_length=10000, allow_blank=True, required=False)

    class Meta:
        model = MedicalRecord
        fields = ["complaint", "diagnosis", "notes", "vitals", "correction_reason"]

    def validate_vitals(self, value):
        if not isinstance(value, dict) or len(value) > 20:
            raise serializers.ValidationError(
                "Enter at most 20 named vital measurements."
            )
        if any(
            not isinstance(k, str)
            or len(k) > 60
            or not isinstance(v, (str, int, float))
            or len(str(v)) > 100
            for k, v in value.items()
        ):
            raise serializers.ValidationError(
                "Each measurement must have a short name and value."
            )
        return value


class EntryInput(serializers.ModelSerializer):
    class Meta:
        model = ClinicalEntry
        fields = ["name", "notes"]


class PrescriptionItemInput(serializers.Serializer):
    medicine = serializers.CharField(max_length=200)
    dosage = serializers.CharField(max_length=250)
    instructions = serializers.CharField(max_length=1000, allow_blank=True, default="")
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal(".001")
    )
    unit = serializers.CharField(max_length=40)

    def validate_unit(self, value):
        return value.strip().lower()


class PrescriptionInput(serializers.Serializer):
    record_id = serializers.UUIDField(required=False, allow_null=True)
    valid_until = serializers.DateTimeField()
    notes = serializers.CharField(max_length=2000, allow_blank=True, default="")
    items = PrescriptionItemInput(many=True, min_length=1, max_length=30)

    def validate_valid_until(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Validity must be in the future.")
        return value


class DispenseItemInput(serializers.Serializer):
    prescription_item_id = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal(".001")
    )
    unit = serializers.CharField(max_length=40)


class DispenseInput(serializers.Serializer):
    items = DispenseItemInput(many=True, min_length=1, max_length=30)

    def validate_items(self, items):
        identifiers = [item["prescription_item_id"] for item in items]
        if len(set(identifiers)) != len(identifiers):
            raise serializers.ValidationError(
                "Each prescription item must occur only once."
            )
        return items


class ReviewInput(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)
    evidence_reviewed = serializers.CharField(max_length=1000, required=False)
    valid_until = serializers.DateTimeField(required=False)


class ApplicationFilterInput(serializers.Serializer):
    role = serializers.ChoiceField(choices=["doctor", "pharmacist"], required=False)
    status = serializers.ChoiceField(
        choices=["pending", "approved", "rejected", "suspended", "expired"],
        required=False,
    )
    search = serializers.CharField(max_length=100, allow_blank=True, required=False)


def validated(serializer_class, data, **kwargs):
    serializer = serializer_class(data=data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class PatientLookupInput(serializers.Serializer):
    identifier = serializers.CharField(max_length=100)


class ReportInput(serializers.Serializer):
    title = serializers.CharField(max_length=200, allow_blank=True, default="")
    record_id = serializers.UUIDField(required=False, allow_null=True)


class DoctorProfileInput(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)

    def validate(self, data):
        unsupported = set(self.initial_data) - set(self.fields)
        if unsupported:
            raise serializers.ValidationError(
                {
                    key: "This field cannot be changed here."
                    for key in sorted(unsupported)
                }
            )
        if not data:
            raise serializers.ValidationError(
                "Provide a name or contact phone to update."
            )
        return data
