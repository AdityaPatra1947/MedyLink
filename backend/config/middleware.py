import uuid
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware


def csrf_failure(request, reason=""):
    return JsonResponse(
        {
            "code": "csrf_failed",
            "detail": "Refresh this page and try again.",
            "request_id": getattr(request, "request_id", ""),
        },
        status=403,
    )


class EnforceCSRFMiddleware(CsrfViewMiddleware):
    """DRF marks APIViews exempt; cookie APIs still require CSRF for every mutation."""

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if request.path.startswith("/api/"):

            def protected_callback(request):
                pass

            return super().process_view(
                request, protected_callback, callback_args, callback_kwargs
            )
        return super().process_view(request, callback, callback_args, callback_kwargs)


class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["Referrer-Policy"] = "no-referrer"
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store, private, max-age=0"
            response["Pragma"] = "no-cache"
            response["Vary"] = "Cookie"
        return response
