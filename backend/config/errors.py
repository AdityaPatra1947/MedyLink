from django.conf import settings
from django.db import OperationalError, ProgrammingError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    request = context.get("request")
    request_id = getattr(request, "request_id", "")
    if response is not None:
        original = response.data
        code = getattr(exc, "default_code", "request_failed")
        detail = original.get("detail") if isinstance(original, dict) else None
        if detail is not None:
            code = getattr(detail, "code", code)
        response.data = {
            "code": str(code),
            "detail": str(detail or "Check the highlighted fields and try again."),
            "request_id": request_id,
        }
        if detail is None:
            response.data["errors"] = original
        return response
    if (
        isinstance(exc, (OperationalError, ProgrammingError))
        or settings.DATABASES["default"]["ENGINE"] == "django.db.backends.dummy"
    ):
        return Response(
            {
                "code": "database_unavailable",
                "detail": "The database is not ready. Configure Neon and run migrations.",
                "request_id": request_id,
            },
            status=503,
        )
    return Response(
        {
            "code": "server_error",
            "detail": "The request could not be completed. Please try again.",
            "request_id": request_id,
        },
        status=500,
    )
