from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def health(request):
    return JsonResponse({"status": "ok", "service": "MedyLink"})


def ready(request):
    if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.dummy":
        return JsonResponse(
            {
                "status": "setup_required",
                "detail": "Set DATABASE_URL in backend/.env to your Neon connection string, then run migrations.",
            },
            status=503,
        )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM accounts_user LIMIT 1")
    except Exception:
        return JsonResponse(
            {
                "status": "unavailable",
                "detail": "Database is not ready. Check the connection and run migrations.",
            },
            status=503,
        )
    return JsonResponse({"status": "ok", "database": connection.vendor})
