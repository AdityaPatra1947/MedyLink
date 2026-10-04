import hashlib
import time

from config.throttling import SharedRateThrottle
from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import BaseThrottle


class AuthIPThrottle(SharedRateThrottle):
    pass


class AuthIdentityThrottle(BaseThrottle):
    """Atomic account-level counters complement the shared proxy/IP limit."""

    def allow_request(self, request, view):
        if getattr(settings, "TESTING", False):
            return True
        if not isinstance(request.data, dict):
            return True
        email = str(request.data.get("email", "")).strip().lower()[:254]
        if not email:
            return True
        ident = hashlib.sha256(email.encode()).hexdigest()
        key = f"auth-account:{ident}:{int(time.time() // 60)}"
        cache.add(key, 0, timeout=65)
        return cache.incr(key) <= 10

    def wait(self):
        return 60
