from django.urls import include, path
from .health import health, ready
from .schema import schema

urlpatterns = [
    path("api/v1/health/", health),
    path("api/v1/ready/", ready),
    path("api/v1/schema/", schema),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/admin/analytics/", include("analytics.urls")),
    path("api/v1/", include("clinic.urls")),
]
