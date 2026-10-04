"""Own-patient dashboard facts, without clinical scoring or risk inference."""

import math
import re
from decimal import Decimal

from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .health_tracking import health_metrics
from .report_formats import MONTHLY_FORMATS
from .models import (
    AuditEvent,
    ClinicalEntry,
    MedicalRecord,
    MedicalReport,
    Prescription,
    PrescriptionItem,
)

_NUMBER = r"(?:\d+(?:\.\d*)?|\.\d+)"
_BP = re.compile(
    rf"^\s*({_NUMBER})\s*/\s*({_NUMBER})\s*(?:mm\s*hg)?\s*$", re.IGNORECASE
)
_GLUCOSE = re.compile(rf"^\s*({_NUMBER})\s*(?:mg\s*/\s*dl)?\s*$", re.IGNORECASE)


def positive_number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return int(number) if number.is_integer() else number


def blood_pressure(vitals):
    value = vitals.get("blood_pressure")
    if isinstance(value, str) and (match := _BP.fullmatch(value)):
        systolic, diastolic = map(positive_number, match.groups())
    else:
        systolic = positive_number(vitals.get("systolic"))
        diastolic = positive_number(vitals.get("diastolic"))
    if systolic is None or diastolic is None:
        return None
    return {"systolic": systolic, "diastolic": diastolic, "unit": "mmHg"}


def blood_sugar(vitals):
    for key in ("glucose_mg_dl", "blood_sugar", "glucose"):
        if key not in vitals:
            continue
        value = vitals[key]
        if isinstance(value, str):
            match = _GLUCOSE.fullmatch(value)
            value = match[1] if match else None
        number = positive_number(value)
        if number is not None:
            context = vitals.get("glucose_context")
            return {
                "value": number,
                "unit": "mg/dL",
                "context": context.strip()[:100]
                if isinstance(context, str) and context.strip()
                else None,
            }
    return None


def vital_trends(patient):
    # Corrections replace content, not the measurement date of the consultation.
    # Resolve root dates once without an extra query for every correction chain.
    metadata = {
        row["id"]: row
        for row in MedicalRecord.objects.filter(patient=patient).values(
            "id", "created_at", "correction_of_id"
        )
    }
    root_dates = {}

    def original_date(record_id):
        chain, seen = [], set()
        current = record_id
        while current in metadata and current not in seen and current not in root_dates:
            chain.append(current)
            seen.add(current)
            parent = metadata[current]["correction_of_id"]
            if parent not in metadata:
                break
            current = parent
        stamp = root_dates.get(current) or min(
            metadata[key]["created_at"] for key in chain
        )
        for key in chain:
            root_dates[key] = stamp
        return stamp

    superseded = {
        row["correction_of_id"] for row in metadata.values() if row["correction_of_id"]
    }
    records = (
        MedicalRecord.objects.filter(patient=patient)
        .exclude(pk__in=superseded)
        .values("id", "doctor__name", "vitals")
    )
    trends = {"blood_pressure": [], "blood_sugar": []}
    extracted = []
    for report in MedicalReport.objects.filter(
        patient=patient, extraction__status="extracted",
        extraction__format__in=MONTHLY_FORMATS,
    ).select_related("uploaded_by").iterator(chunk_size=64):
        data = report.extraction
        try:
            measured = parse_datetime(data.get("measured_at", ""))
        except (ValueError, TypeError):
            continue
        if measured is None or timezone.is_naive(measured) or measured > timezone.now():
            continue
        extracted.append((report, measured, data))
    report_readings = {"blood_pressure": [], "blood_sugar": []}
    for report, measured, data in extracted:
        for key in report_readings:
            reading = data.get(key)
            if not isinstance(reading, dict):
                continue
            report_readings[key].append({
                **reading, "record_id": str(report.record_id) if report.record_id else None,
                "report_id": str(report.id), "report_title": report.title or report.name,
                "view_url": f"/api/v1/reports/{report.id}/view/",
                "recorded_at": measured.isoformat(), "author": report.uploaded_by.name,
                "source": "Monthly PDF report",
            })
    for record in records.iterator(chunk_size=64):
        # A record committed after the metadata read belongs to the next refresh.
        if record["id"] not in metadata:
            continue
        vitals = record["vitals"]
        if not isinstance(vitals, dict):
            continue
        meta = {
            "record_id": str(record["id"]),
            "recorded_at": original_date(record["id"]).isoformat(),
            "author": record["doctor__name"],
            "source": "Consultation",
        }
        for key, parser in (
            ("blood_pressure", blood_pressure),
            ("blood_sugar", blood_sugar),
        ):
            if reading := parser(vitals):
                # An attached PDF carrying the same dated reading is its evidence,
                # not a second observation. Different dated measurements remain.
                duplicate = any(
                    row["record_id"] == str(record["id"])
                    and parse_datetime(row["recorded_at"]).date() == original_date(record["id"]).date()
                    and all(row.get(field) == reading.get(field) for field in (
                        ("systolic", "diastolic") if key == "blood_pressure" else ("value",)
                    ))
                    for row in report_readings[key]
                )
                if not duplicate:
                    trends[key].append({**meta, **reading})
    for key in trends:
        trends[key].extend(report_readings[key])
        trends[key].sort(key=lambda point: (
            parse_datetime(point["recorded_at"]), point.get("report_id") or point.get("record_id") or ""
        ))
        trends[key] = trends[key][-24:]
    return trends


def active_prescription_count(patient, now):
    # Aggregate per item so multiple dispenses do not duplicate prescribed quantity.
    available_items = (
        PrescriptionItem.objects.filter(
            prescription__patient=patient,
            prescription__cancelled_at__isnull=True,
            prescription__valid_until__gt=now,
        )
        .annotate(dispensed=Coalesce(Sum("dispenses__quantity"), Value(Decimal(0))))
        .filter(quantity__gt=F("dispensed"))
        .values("prescription_id")
    )
    return Prescription.objects.filter(patient=patient, pk__in=available_items).count()


def recent_notifications(patient):
    notifications = []
    sources = (
        (MedicalRecord, "record", "records", "complaint"),
        (MedicalReport, "report", "reports", "title"),
        (Prescription, "prescription", "prescriptions", None),
    )
    for model, kind, target, title_field in sources:
        fields = ["id", "created_at"]
        if title_field:
            fields.append(title_field)
        for row in (
            model.objects.filter(patient=patient)
            .order_by("-created_at", "-id")
            .values(*fields)[:5]
        ):
            title = row.get(title_field, "") if title_field else "Prescription issued"
            if kind == "record":
                title = f"Consultation: {title}"
            elif kind == "report":
                title = (
                    f"Report uploaded: {title}"
                    if title
                    else "New medical report uploaded"
                )
            notifications.append(
                {
                    "id": f"{kind}:{row['id']}",
                    "kind": kind,
                    "title": title,
                    "created_at": row["created_at"].isoformat(),
                    "target_tab": target,
                }
            )
    return sorted(
        notifications, key=lambda row: (row["created_at"], row["id"]), reverse=True
    )[:5]


def dashboard_data(patient, user):
    trends = vital_trends(patient)
    data = {
        "counts": {
            "records": MedicalRecord.objects.filter(patient=patient).count(),
            "active_prescriptions": active_prescription_count(patient, timezone.now()),
            "conditions": ClinicalEntry.objects.filter(
                patient=patient, kind="condition", resolved_at__isnull=True
            ).count(),
            "reports": MedicalReport.objects.filter(patient=patient).count(),
            "report_downloads": AuditEvent.objects.filter(
                patient=patient, actor=user, event="report.download", outcome="success"
            ).count(),
        },
        "latest": {key: rows[-1] if rows else None for key, rows in trends.items()},
        "trends": trends,
        "recent_notifications": recent_notifications(patient),
    }
    data.update(health_metrics(patient, trends, data["counts"]["conditions"]))
    return data
