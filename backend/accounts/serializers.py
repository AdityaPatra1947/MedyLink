from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User


def check_password_strength(password, user):
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": exc.messages}) from None


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        min_length=8, max_length=1024, trim_whitespace=False, write_only=True
    )
    password_confirm = serializers.CharField(
        max_length=1024, trim_whitespace=False, write_only=True
    )
    phone = serializers.CharField(
        max_length=30, allow_blank=True, required=False, default=""
    )
    role = serializers.ChoiceField(choices=["patient", "doctor", "pharmacist"])
    consent = serializers.BooleanField()
    privacy_version = serializers.CharField(max_length=30, default="1.0")
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=["", "female", "male", "other", "prefer_not_to_say"], required=False
    )
    address = serializers.CharField(max_length=500, allow_blank=True, required=False)
    blood_group = serializers.ChoiceField(
        choices=["unknown", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
        required=False,
    )
    emergency_contact = serializers.CharField(
        max_length=250, allow_blank=True, required=False
    )
    qualification = serializers.CharField(
        max_length=150, allow_blank=True, required=False
    )
    specialty = serializers.CharField(max_length=150, allow_blank=True, required=False)
    registration_number = serializers.CharField(
        max_length=100, allow_blank=True, required=False
    )
    registering_body = serializers.CharField(
        max_length=150, allow_blank=True, required=False
    )
    practice_address = serializers.CharField(
        max_length=500, allow_blank=True, required=False
    )
    clinic_name = serializers.CharField(
        max_length=180, allow_blank=True, required=False
    )
    years_experience = serializers.IntegerField(
        min_value=0, max_value=80, allow_null=True, required=False
    )
    shop_name = serializers.CharField(max_length=180, allow_blank=True, required=False)
    shop_license = serializers.CharField(
        max_length=100, allow_blank=True, required=False
    )
    shop_license_expires = serializers.DateField(required=False, allow_null=True)
    opening_hours = serializers.CharField(
        max_length=300, allow_blank=True, required=False
    )
    credential_documents = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=False,
        max_length=5,
        write_only=True,
    )
    photo = serializers.FileField(required=False, write_only=True)

    def validate(self, attrs):
        from clinic.serializers import ApplicationInput, ProfileInput
        from clinic.uploads import validate_registration_uploads

        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        if not attrs["consent"]:
            raise serializers.ValidationError(
                {"consent": "Consent to store your records is required."}
            )
        if attrs["privacy_version"] != "1.0":
            raise serializers.ValidationError(
                {"privacy_version": "Please read the current privacy notice."}
            )
        attrs["email"] = attrs["email"].strip().lower()
        check_password_strength(
            attrs["password"], User(email=attrs["email"], name=attrs["name"])
        )
        if attrs["role"] == "patient":
            if not attrs.get("date_of_birth"):
                raise serializers.ValidationError(
                    {"date_of_birth": "Date of birth is required."}
                )
            if attrs.get("credential_documents") or attrs.get("photo"):
                raise serializers.ValidationError(
                    {
                        "credential_documents": "Patient registration does not accept provider files."
                    }
                )
            fields = [
                "date_of_birth",
                "gender",
                "phone",
                "address",
                "blood_group",
                "emergency_contact",
            ]
            profile = ProfileInput(
                data={key: attrs[key] for key in fields if key in attrs}
            )
            profile.is_valid(raise_exception=True)
            attrs["_profile"] = profile.validated_data
        else:
            fields = [
                "qualification",
                "specialty",
                "registration_number",
                "registering_body",
                "practice_address",
                "clinic_name",
                "years_experience",
                "shop_name",
                "shop_license",
                "shop_license_expires",
                "opening_hours",
            ]
            application_data = {key: attrs[key] for key in fields if key in attrs}
            application_data["contact_phone"] = attrs["phone"]
            application = ApplicationInput(
                data=application_data, context={"user": User(role=attrs["role"])}
            )
            application.is_valid(raise_exception=True)
            attrs["_application"] = application.validated_data
            attrs["_uploads"] = validate_registration_uploads(
                attrs.get("credential_documents", []), attrs.get("photo")
            )
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=1024, trim_whitespace=False)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class SixDigitEmailCodeField(serializers.RegexField):
    def __init__(self, **kwargs):
        super().__init__(
            regex=r"\A[0-9]{6}\Z",
            min_length=6,
            max_length=6,
            trim_whitespace=False,
            **kwargs,
        )

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Enter the six-digit code as text.")
        return super().to_internal_value(data)


class EmailVerificationSerializer(EmailSerializer):
    code = SixDigitEmailCodeField(write_only=True)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=20, max_length=200)


class ResetPasswordSerializer(TokenSerializer):
    password = serializers.CharField(
        min_length=8, max_length=1024, trim_whitespace=False
    )


def user_payload(user):
    return {
        "id": str(user.id),
        "account_id": user.account_id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "phone": user.phone,
        "email_verified": user.email_verified,
    }
