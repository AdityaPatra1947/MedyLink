import hashlib
import time
from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import BaseThrottle


class SharedRateThrottle(BaseThrottle):
    """Atomic Redis increment in production; process-local counters only in development."""

    def allow_request(self, request, view):
        if settings.TESTING:
            return True
        path = request.path
        sensitive = "/auth/" in path and request.method != "GET"
        lookup = "/access-requests" in path and request.method == "POST"
        limit = 20 if sensitive else 30 if lookup else 300
        # Nginx overwrites this header. Backend must remain private in production.
        address = request.META.get("HTTP_X_REAL_IP") if not settings.DEBUG else None
        address = address or request.META.get("REMOTE_ADDR", "unknown")
        identity = hashlib.sha256(address.encode()).hexdigest()
        bucket = int(time.time() // 60)
        key = f"rate:{identity}:{'auth' if sensitive else 'lookup' if lookup else 'api'}:{bucket}"
        cache.add(key, 0, timeout=65)
        count = cache.incr(key)
        return count <= limit

    def wait(self):
        return 60
