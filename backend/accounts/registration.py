from clinic.models import ProviderApplication
from clinic.services import own_patient
from clinic.uploads import private_file_batch, save_document
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import AccountToken, User
from .services import audit, send_account_email


def register_account(data, request):
    """Persist the account, role details, files, and email challenge as one unit."""
    try:
        with private_file_batch() as created_paths:
            with transaction.atomic():
                if User.objects.filter(email__iexact=data["email"]).exists():
                    return
                user = User.objects.create_user(
                    email=data["email"],
                    password=data["password"],
                    name=data["name"],
                    phone=data["phone"],
                    role=data["role"],
                    storage_consent_at=timezone.now(),
                    privacy_version=data["privacy_version"],
                )
                if user.role == "patient":
                    patient = own_patient(user)
                    for field, value in data["_profile"].items():
                        setattr(patient, field, value)
                    patient.save()
                else:
                    application = ProviderApplication.objects.create(
                        provider=user, version=1, **data["_application"]
                    )
                    for checked in data["_uploads"]:
                        save_document(application, checked, created_paths)
                send_account_email(user, AccountToken.Purpose.VERIFY_EMAIL)
                audit(user, "account_registered", request)
    except IntegrityError:
        # Only a racing duplicate email is intentionally indistinguishable.
        if not User.objects.filter(email__iexact=data["email"]).exists():
            raise
