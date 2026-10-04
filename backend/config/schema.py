"""Small, inspectable OpenAPI description for the cookie-authenticated REST API."""

import re

from accounts import serializers as account
from clinic import serializers as clinic
from clinic.health_tracking_views import AdherenceInput, LabInput
from django.conf import settings
from django.http import JsonResponse
from django.urls import URLResolver, get_resolver
from rest_framework import serializers


def object_schema(properties=None, required=None):
    result = {"type": "object", "properties": properties or {}}
    if required:
        result["required"] = required
    return result


def scalar(kind="string", **kwargs):
    return {"type": kind, **kwargs}


def field_schema(field):
    if isinstance(field, serializers.ListField):
        result = {"type": "array", "items": field_schema(field.child)}
        if field.max_length is not None:
            result["maxItems"] = field.max_length
        return result
    if isinstance(field, serializers.FileField):
        return scalar(format="binary")
    if isinstance(field, serializers.ListSerializer):
        return {"type": "array", "items": serializer_schema(field.child)}
    if isinstance(field, serializers.Serializer):
        return serializer_schema(field)
    if isinstance(field, serializers.ChoiceField):
        return scalar(enum=list(field.choices))
    if isinstance(field, serializers.BooleanField):
        return scalar("boolean")
    if isinstance(field, serializers.IntegerField):
        result = scalar("integer")
        if field.min_value is not None:
            result["minimum"] = field.min_value
        if field.max_value is not None:
            result["maximum"] = field.max_value
        return result
    if isinstance(field, serializers.DecimalField):
        return scalar(
            description="Positive decimal quantity as a string; up to three decimal places."
        )
    if isinstance(field, serializers.DateTimeField):
        return scalar(format="date-time")
    if isinstance(field, serializers.DateField):
        return scalar(format="date")
    if isinstance(field, serializers.UUIDField):
        return scalar(format="uuid")
    if isinstance(field, serializers.JSONField):
        return {"type": "object", "additionalProperties": True}
    result = scalar()
    if getattr(field, "max_length", None):
        result["maxLength"] = field.max_length
    if getattr(field, "allow_null", False):
        result["nullable"] = True
    return result


def serializer_schema(serializer):
    fields = {
        name: value for name, value in serializer.fields.items() if not value.read_only
    }
    return object_schema(
        {name: field_schema(value) for name, value in fields.items()},
        [name for name, value in fields.items() if value.required],
    )


REQUESTS = {
    "RegisterView": account.RegisterSerializer,
    "LoginView": account.LoginSerializer,
    "VerifyEmailView": account.EmailVerificationSerializer,
    "EmailActionView": account.EmailSerializer,
    "ForgotPasswordView": account.EmailSerializer,
    "ResetPasswordView": account.ResetPasswordSerializer,
    "ProfileView": clinic.ProfileInput,
    "DoctorProfileView": clinic.DoctorProfileInput,
    "PatientLookupView": clinic.PatientLookupInput,
    "ReportsView": clinic.ReportInput,
    "ApplicationView": clinic.ApplicationInput,
    "ReviewApplicationView": clinic.ReviewInput,
    "RecordsView": clinic.RecordInput,
    "CorrectionView": clinic.RecordInput,
    "EntriesView": clinic.EntryInput,
    "PrescriptionsView": clinic.PrescriptionInput,
    "DispenseView": clinic.DispenseInput,
    "AdherenceView": AdherenceInput,
    "LabsView": LabInput,
}
PUBLIC = {
    "CSRFView",
    "RegisterView",
    "LoginView",
    "EmailActionView",
    "ForgotPasswordView",
    "VerifyEmailView",
    "ResetPasswordView",
    "RefreshView",
    "LogoutView",
}


def operations(patterns, prefix=""):
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from operations(pattern.url_patterns, route)
            continue
        cls = getattr(pattern.callback, "view_class", None)
        if cls is None:
            continue
        path_parameters = re.findall(r"<(?:(\w+):)?(\w+)>", route)
        path = "/" + re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", route)
        details = {}
        for method in ["get", "post", "put", "patch", "delete"]:
            if not hasattr(cls, method):
                continue
            name = cls.__name__
            summary = re.sub(r"(?<!^)(?=[A-Z])", " ", name.removesuffix("View"))
            op = {
                "summary": summary,
                "operationId": method
                + "_"
                + re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_"),
                "tags": ["Accounts" if "/auth/" in path else "Clinical workflow"],
                "security": [] if name in PUBLIC else [{"cookieAuth": []}],
                "parameters": [
                    {
                        "name": n,
                        "in": "path",
                        "required": True,
                        "schema": scalar(**({"format": "uuid"} if t == "uuid" else {})),
                    }
                    for t, n in path_parameters
                ],
                "responses": {
                    "200": {
                        "description": "Success. See the clinic API contract for role-specific response fields."
                    },
                    "400": {"$ref": "#/components/responses/Error"},
                    "401": {"$ref": "#/components/responses/Error"},
                    "403": {"$ref": "#/components/responses/Error"},
                    "404": {"$ref": "#/components/responses/Error"},
                    "409": {"$ref": "#/components/responses/Error"},
                    "429": {"$ref": "#/components/responses/Error"},
                },
            }
            health_descriptions = {
                "PatientDashboardView": "Verified patient only. Returns database counts, latest consultation vitals and trends, recent notifications, and health metrics. Score and risk remain null until a valid versioned policy and all fresh required observations are available. Missing adherence, laboratory data and regional source availability remain explicit. See docs/PATIENT_HEALTH_DATA.md.",
                "AdherenceView": "Verified patient only; own daily dose logs for today and the preceding 29 UTC dates. GET returns results and a nullable weighted adherence summary. PUT upserts the supplied date and returns the same shape; use JSON integers, 1–10000 scheduled doses and 0–scheduled taken doses. Missing days are unknown. See docs/PATIENT_HEALTH_DATA.md.",
                "LabsView": "Verified patients use /patients/me/labs/ for their own observations; currently approved doctors use /patients/{patient_id}/labs/. Pharmacists and administrators cannot access these endpoints. GET returns paginated observations and latest-per-test-and-unit summary; POST appends an attributed observation (201), optionally linked to a report belonging to the same patient. Reference limits are supplied, never inferred; missing references produce an unknown flag. See docs/PATIENT_HEALTH_DATA.md.",
            }
            if name in health_descriptions:
                op["description"] = health_descriptions[name]
            if method == "get":
                op["parameters"].append(
                    {
                        "name": "page",
                        "in": "query",
                        "description": "For list endpoints only; 50 results per page.",
                        "schema": {"type": "integer", "minimum": 1},
                    }
                )
                if name in {"PatientDashboardView", "AdherenceView"}:
                    op["parameters"] = [
                        parameter
                        for parameter in op["parameters"]
                        if parameter["name"] != "page"
                    ]
                if name == "AdminApplicationsView" and not path_parameters:
                    op["parameters"].extend(
                        [
                            {
                                "name": "role",
                                "in": "query",
                                "schema": scalar(enum=["doctor", "pharmacist"]),
                            },
                            {
                                "name": "status",
                                "in": "query",
                                "schema": scalar(
                                    enum=[
                                        "pending",
                                        "approved",
                                        "rejected",
                                        "suspended",
                                        "expired",
                                    ]
                                ),
                            },
                            {
                                "name": "search",
                                "in": "query",
                                "schema": scalar(maxLength=100),
                            },
                        ]
                    )
            else:
                op["parameters"].append(
                    {
                        "name": "X-CSRFToken",
                        "in": "header",
                        "required": True,
                        "schema": scalar(),
                        "description": "Get from GET /api/v1/auth/csrf/ with the same browser cookies.",
                    }
                )
                body = (
                    serializer_schema(REQUESTS[name]())
                    if name in REQUESTS
                    else object_schema()
                )
                if name in {"AdherenceView", "LabsView"}:
                    body["additionalProperties"] = False
                if name == "LabsView":
                    for field in ("value", "reference_low", "reference_high"):
                        nullable = field != "value"
                        body["properties"][field] = {
                            "anyOf": [
                                scalar(nullable=nullable),
                                scalar("number", nullable=nullable),
                            ],
                            "description": "Finite decimal number or decimal string, up to 16 digits in total and five decimal places; reference bounds may be null.",
                        }
                    body["properties"]["report_id"]["nullable"] = True
                if name in {
                    "ResolveEntryView",
                    "SuspendProviderView",
                    "CancelPrescriptionView",
                }:
                    body = object_schema({"reason": scalar(maxLength=1000)}, ["reason"])
                if name == "ValidateDocumentView":
                    body = object_schema(
                        {"reason": scalar(), "safe": scalar("boolean")},
                        ["reason", "safe"],
                    )
                if name == "VerifyEmailView":
                    body["properties"]["code"].update(
                        {
                            "type": "string",
                            "pattern": "^[0-9]{6}$",
                            "minLength": 6,
                            "maxLength": 6,
                            "example": "003721",
                        }
                    )
                    op["description"] = (
                        "Verify an email address using its six-digit email code, valid for 10 minutes. Preserve leading zeros. Five incorrect attempts exhaust the challenge. Code verification is single-use and never signs the user in. Legacy token-only requests are rejected."
                    )
                if name == "EmailActionView":
                    op["description"] = (
                        "Request a new six-digit email verification code. Sending is limited to once per account every 60 seconds. Unknown, verified, and cooldown-limited accounts receive the same generic response. A newly sent code replaces the previous one."
                    )
                    op["responses"]["200"] = {
                        "description": "Generic verification-code delivery response.",
                        "content": {
                            "application/json": {
                                "schema": object_schema(
                                    {
                                        "detail": scalar(),
                                        "resend_after": scalar("integer", enum=[60]),
                                    },
                                    ["detail", "resend_after"],
                                )
                            }
                        },
                    }
                content_type = "application/json"
                if name == "RegisterView":
                    content_type = "multipart/form-data"
                    body["description"] = (
                        "Common fields include password_confirm. Patients require an adult date_of_birth. Doctors require qualification, specialty, registration_number, registering_body, practice_address and credential_documents. Pharmacists require registration_number, registering_body, shop_name, practice_address, shop_license, shop_license_expires and credential_documents. Upload 1–5 PDF/JPEG/PNG credential files, each up to 5 MiB and 20 MiB combined. Optional JPEG/PNG photo up to 2 MiB. Email verification uses a six-digit email code with a 10-minute expiry; no SMS verification. Patient JSON requests are also supported."
                    )
                if name in {"ReportsView", "PatientPhotoView"}:
                    content_type = "multipart/form-data"
                    body = object_schema(
                        {
                            "file": scalar(
                                format="binary",
                                description="JPEG/PNG up to 2 MiB for photos; PDF/JPEG/PNG up to 10 MiB for reports.",
                            ),
                            **(
                                {
                                    "title": scalar(maxLength=200),
                                    "record_id": scalar(format="uuid", nullable=True),
                                }
                                if name == "ReportsView"
                                else {}
                            ),
                        },
                        ["file"],
                    )
                if name == "UploadDocumentView":
                    content_type = "multipart/form-data"
                    body = object_schema(
                        {
                            "file": scalar(
                                format="binary",
                                description="PDF, JPEG, PNG; maximum 5 MB.",
                            ),
                            "kind": scalar(
                                enum=["credential", "photo"],
                                description="Defaults to credential. A photo is optional and never counts as approval evidence.",
                            ),
                        },
                        ["file"],
                    )
                if method != "delete":
                    op["requestBody"] = {
                        "required": True,
                        "content": {content_type: {"schema": body}},
                    }
                    if name == "RegisterView":
                        op["requestBody"]["content"]["application/json"] = {
                            "schema": body
                        }
                if name == "DispenseView":
                    op["parameters"].append(
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": True,
                            "schema": scalar(maxLength=100),
                        }
                    )
                if method == "post":
                    op["responses"].update(
                        {
                            "201": {"description": "Resource created."},
                            "202": {
                                "description": "Request accepted; generic non-revealing response."
                            },
                        }
                    )
                if method == "delete":
                    op["responses"]["204"] = {"description": "Session revoked."}
            if "pdf" in path:
                op["responses"]["200"] = {
                    "description": "Authorized PDF download.",
                    "content": {"application/pdf": {"schema": scalar(format="binary")}},
                }
            details[method] = op
        yield path, details


def schema(request):
    """Public interface description only; no user/database values are exposed."""
    error = object_schema(
        {
            "code": scalar(),
            "detail": scalar(),
            "request_id": scalar(format="uuid"),
            "errors": object_schema(),
        }
    )
    return JsonResponse(
        {
            "openapi": "3.0.3",
            "info": {
                "title": "MedyLink",
                "version": "1.0.0",
                "description": "Same-origin cookie API. Bootstrap CSRF before mutations. Provider access requires verified email and current administrator-approved credentials. Doctors access clinical records directly; pharmacists are restricted to prescriptions and relevant allergy information. Response field documentation: backend/clinic/API.md.",
            },
            "paths": dict(operations(get_resolver().url_patterns)),
            "components": {
                "securitySchemes": {
                    "cookieAuth": {
                        "type": "apiKey",
                        "in": "cookie",
                        "name": settings.AUTH_ACCESS_COOKIE_NAME,
                    }
                },
                "responses": {
                    "Error": {
                        "description": "Request denied or invalid.",
                        "content": {"application/json": {"schema": error}},
                    }
                },
            },
        }
    )
