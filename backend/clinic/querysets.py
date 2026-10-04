"""Bounded-query loading for clinical lists with nested prescriptions."""

from decimal import Decimal

from django.db.models import Prefetch, Sum, Value
from django.db.models.functions import Coalesce

from .models import ClinicalEntry, PrescriptionItem


def prescription_details(queryset):
    return queryset.select_related("patient__user", "doctor", "application").prefetch_related(
        Prefetch("items", queryset=PrescriptionItem.objects.annotate(
            dispensed_total=Coalesce(Sum("dispenses__quantity"), Value(Decimal(0))),
        )),
        Prefetch("patient__clinicalentry_set", to_attr="active_allergies", queryset=(
            ClinicalEntry.objects.filter(kind="allergy", resolved_at__isnull=True)
            .select_related("author").order_by("-created_at")[:100]
        )),
    )
