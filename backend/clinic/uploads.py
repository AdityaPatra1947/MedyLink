"""Private, bounded uploads shared by registration and provider resubmission."""

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db.models import Sum
from PIL import Image
from rest_framework.exceptions import ValidationError

from .models import ProviderDocument

MIB = 1024 * 1024
MAX_CREDENTIAL_FILES = 5
MAX_CREDENTIAL_TOTAL = 20 * MIB


@dataclass
class CheckedUpload:
    upload: object
    suffix: str
    content_type: str
    kind: str


def validate_upload(upload, kind="credential"):
    if kind not in {"credential", "photo", "report"}:
        raise ValidationError({"kind": "Choose credential, photo or report."})
    limit = {"photo": 2, "credential": 5, "report": 10}[kind] * MIB
    if (
        not upload
        or not hasattr(upload, "read")
        or upload.size < 8
        or upload.size > limit
    ):
        raise ValidationError(
            f"Upload a {'JPEG or PNG photo up to 2' if kind == 'photo' else 'PDF, JPEG or PNG document up to ' + str(limit // MIB)} MiB."
        )
    suffix = Path(upload.name).suffix.lower()
    signature = upload.read(16)
    upload.seek(0)
    types = {
        ".pdf": ("application/pdf", signature.startswith(b"%PDF-")),
        ".png": ("image/png", signature.startswith(b"\x89PNG\r\n\x1a\n")),
        ".jpg": ("image/jpeg", signature.startswith(b"\xff\xd8\xff")),
        ".jpeg": ("image/jpeg", signature.startswith(b"\xff\xd8\xff")),
    }
    if (
        suffix not in types
        or not types[suffix][1]
        or (kind == "photo" and suffix == ".pdf")
    ):
        raise ValidationError("File contents do not match a supported extension.")
    if suffix != ".pdf":
        try:
            with Image.open(upload) as image:
                if image.width * image.height > 25000000:
                    raise ValueError("Image too large")
                image.verify()
        except Exception:
            raise ValidationError("Image validation failed.") from None
        finally:
            upload.seek(0)
    return CheckedUpload(upload, suffix, types[suffix][0], kind)


def validate_registration_uploads(credentials, photo=None):
    if not credentials or len(credentials) > MAX_CREDENTIAL_FILES:
        raise ValidationError(
            {
                "credential_documents": "Upload between one and five credential documents."
            }
        )
    if sum(file.size for file in credentials) > MAX_CREDENTIAL_TOTAL:
        raise ValidationError(
            {"credential_documents": "Credential documents must total at most 20 MiB."}
        )
    checked = []
    for file in credentials:
        try:
            checked.append(validate_upload(file))
        except ValidationError as exc:
            raise ValidationError({"credential_documents": exc.detail}) from None
    if photo:
        try:
            checked.append(validate_upload(photo, "photo"))
        except ValidationError as exc:
            raise ValidationError({"photo": exc.detail}) from None
    return checked


@contextmanager
def private_file_batch():
    """Enclose the DB transaction so files are removed even when its commit fails."""
    paths = []
    try:
        yield paths
    except BaseException:
        for path in paths:
            path.unlink(missing_ok=True)
        raise


def save_document(application, checked, created_paths):
    """The caller must hold the provider row lock and use private_file_batch."""
    if checked.kind not in ("credential", "photo"):
        raise ValidationError({"kind": "Choose credential or photo."})
    docs = application.documents.filter(kind=checked.kind)
    if docs.count() >= (1 if checked.kind == "photo" else MAX_CREDENTIAL_FILES):
        raise ValidationError(
            "A submission allows five credential documents and one optional photo."
        )
    if (
        checked.kind == "credential"
        and (docs.aggregate(total=Sum("size_bytes"))["total"] or 0)
        + checked.upload.size
        > MAX_CREDENTIAL_TOTAL
    ):
        raise ValidationError("Credential documents must total at most 20 MiB.")
    storage_name = save_private_upload(checked, created_paths)
    return ProviderDocument.objects.create(
        application=application,
        name=Path(checked.upload.name).name[:180],
        storage_name=storage_name,
        content_type=checked.content_type,
        kind=checked.kind,
        size_bytes=checked.upload.size,
    )


def save_private_upload(checked, created_paths):
    """Write a generated private name; caller owns rollback cleanup and DB transaction."""
    root = Path(settings.PRIVATE_MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    storage_name = str(uuid.uuid4()) + checked.suffix
    destination = root / storage_name
    created_paths.append(destination)
    with destination.open("xb") as file:
        for chunk in checked.upload.chunks():
            file.write(chunk)
    return storage_name
