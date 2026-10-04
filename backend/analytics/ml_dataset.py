"""Read current clinical tables into private, pseudonymous ML snapshots.

This module never writes clinical data or the original analytics import. Only
coarse station locations and aggregate counts are allowed out through the API.
"""

import hashlib
import hmac
import json
import math
import re
from collections import defaultdict
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

from clinic.dashboard import blood_pressure, blood_sugar
from clinic.models import (
    ClinicalEntry,
    LabResult,
    MedicalRecord,
    MedicalReport,
    MedicationAdherenceLog,
    Patient,
)
from clinic.report_formats import MONTHLY_FORMATS
from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from .importing import DISEASE_LABELS
from .models import DatasetBatch, PatientAreaObservation
from .services import safe_count

MAX_ROWS = 75000
MAX_PATIENTS = 5000
ML_DISEASE_LABELS = {**DISEASE_LABELS, "UNKNOWN": "Other or uncoded condition"}
ALIASES = {
    "DENGUE": ("dengue",), "INFLUENZA": ("influenza", "flu"),
    "ASTHMA": ("asthma",), "GASTROENTERITIS": ("gastroenteritis",),
    "HYPERTENSION": ("hypertension",), "TYPE2_DIABETES": ("type 2 diabetes", "type ii diabetes", "diabetes mellitus", "t2dm"),
    "ANEMIA": ("anemia", "anaemia"), "HYPOTHYROIDISM": ("hypothyroidism",),
    "MALARIA": ("malaria",), "OSTEOARTHRITIS": ("osteoarthritis",),
}
SYMPTOM_FLAGS = ("fever", "cough", "joint_pain", "vomiting", "fatigue", "breathlessness", "headache", "rash")


def selected_disease_codes(filters):
    """OR between chosen diseases; optional text narrows that selection."""
    codes = set(filter(None, filters.get("disease_codes", "").split(",")))
    if filters.get("disease_code"):
        codes.add(filters["disease_code"])
    search = filters.get("disease_search", "").strip().casefold()
    if search:
        matches = {code for code, label in ML_DISEASE_LABELS.items() if search in label.casefold() or search in code.replace("_", " ").casefold()}
        return codes & matches if codes else matches
    return codes or None


def finite(value, minimum=None, maximum=None):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(number) or (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        return None
    return number


def timestamp(value):
    try:
        stamp = parse_datetime(value) if isinstance(value, str) else value
        if not isinstance(stamp, datetime):
            return None
        return (timezone.make_aware(stamp, dt_timezone.utc) if timezone.is_naive(stamp) else stamp).astimezone(dt_timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def recognized_diseases(text):
    """Limited curated coding of clinician text, not inferred diagnoses or NLP."""
    text = str(text or "").casefold()
    found = set()
    for code, aliases in ALIASES.items():
        for alias in aliases:
            for match in re.finditer(r"\b" + re.escape(alias) + r"\b", text):
                prefix = text[max(0, match.start() - 45):match.start()]
                if not re.search(r"(?:no|without|denies|ruled out|family history of)\s+(?:\w+\s+){0,3}$", prefix):
                    found.add(code)
    return found


def bounded(query):
    rows = list(query[:MAX_ROWS + 1])
    if len(rows) > MAX_ROWS:
        raise ValidationError("This demonstration supports at most 75,000 rows per clinical source. Narrow the dataset before training.")
    return rows


def resolve_ml_filters(data):
    batch = get_object_or_404(DatasetBatch, key=data["dataset_id"], synthetic=True)
    code, station, line = data.get("disease_code", ""), data.get("station_id", ""), data.get("line", "")
    codes = set(filter(None, data.get("disease_codes", "").split(","))) | ({code} if code else set())
    if codes - set(ML_DISEASE_LABELS):
        raise ValidationError({"disease_code": "Choose a listed disease."})
    if station:
        area = batch.stations.filter(key=station).first()
        if area is None or (line and line not in area.lines):
            raise ValidationError({"station_id": "Choose a station in this dataset and selected line."})
    filters = {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in data.items()}
    return batch, filters


def in_window(stamp, filters):
    day = stamp.date().isoformat()
    return (not filters.get("date_from") or day >= filters["date_from"]) and (not filters.get("date_to") or day <= filters["date_to"])


def build_dataset(batch, filters):
    """Return history for retrospective training and current as-of cohort snapshots.

    A correction changes current content without creating a second encounter. The
    original content remains the historical feature snapshot; later corrections,
    reports, labs and dose logs cannot be backfilled into an earlier prediction.
    """
    now = timezone.now()
    cutoff = min(now, datetime.combine(datetime.fromisoformat(filters["date_to"]).date(), time.max, tzinfo=dt_timezone.utc)) if filters.get("date_to") else now
    areas = list(PatientAreaObservation.objects.filter(batch=batch).select_related("station").only(
        "patient_id", "latitude", "longitude", "station_id",
        "station__key", "station__name", "station__lines", "station__latitude", "station__longitude",
    ).order_by("patient_id")[:MAX_PATIENTS + 1])
    if len(areas) > MAX_PATIENTS:
        raise ValidationError("This demonstration supports at most 5,000 mapped patients.")
    area_by_id = {row.patient_id: row for row in areas if (not filters.get("station_id") or row.station.key == filters["station_id"]) and (not filters.get("line") or filters["line"] in row.station.lines)}
    # A selected dataset must never absorb another batch's patients as though
    # they were newly registered. Only genuinely unmapped demo-environment
    # patients can join numeric analyses without a station assignment.
    unmapped = list(Patient.objects.exclude(pk__in=PatientAreaObservation.objects.values("patient_id")).values_list("id", flat=True)[:MAX_PATIENTS + 1])
    other_batch_count = PatientAreaObservation.objects.exclude(batch=batch).exclude(patient_id__in=PatientAreaObservation.objects.filter(batch=batch).values("patient_id")).values("patient_id").distinct().count()
    include_unmapped = bool(getattr(settings, "SYNTHETIC_IMPORT_ALLOWED", False)) and not filters.get("station_id") and not filters.get("line")
    ids = list(area_by_id) + (unmapped if include_unmapped else [])
    if len(ids) > MAX_PATIENTS:
        raise ValidationError("This demonstration supports at most 5,000 selected patients.")
    patients = {row["id"]: row for row in Patient.objects.filter(pk__in=ids).values("id", "date_of_birth", "gender")}
    records = bounded(MedicalRecord.objects.filter(patient_id__in=ids, created_at__lte=cutoff).order_by("created_at", "id").values("id", "patient_id", "created_at", "correction_of_id", "diagnosis", "vitals"))
    reports = bounded(MedicalReport.objects.filter(patient_id__in=ids, created_at__lte=cutoff).order_by("created_at", "id").values("id", "patient_id", "record_id", "created_at", "extraction"))
    lab_query = LabResult.objects.filter(patient_id__in=ids, created_at__lte=cutoff, measured_at__lte=cutoff)
    # Only glucose is read as a fallback feature. Count every lab in SQL so Hb,
    # platelet and other unused result values never cross the DB connection.
    # The row limit still covers ALL labs, including those outside date_from.
    lab_window = Q()
    if filters.get("date_from"):
        lab_window = Q(measured_at__gte=datetime.combine(datetime.fromisoformat(filters["date_from"]).date(), time.min, tzinfo=dt_timezone.utc))
    lab_counts = list(lab_query.values("patient_id").annotate(total=Count("id"), selected=Count("id", filter=lab_window)))
    if sum(row["total"] for row in lab_counts) > MAX_ROWS:
        raise ValidationError("This demonstration supports at most 75,000 rows per clinical source. Narrow the dataset before training.")
    labs = bounded(lab_query.filter(name__icontains="glucose").order_by("measured_at", "created_at").values("patient_id", "name", "unit", "value", "measured_at", "created_at"))
    entries = bounded(ClinicalEntry.objects.filter(patient_id__in=ids, kind="condition", created_at__lte=cutoff).order_by("created_at").values("patient_id", "name", "created_at", "resolved_at"))
    dose_logs = bounded(MedicationAdherenceLog.objects.filter(patient_id__in=ids, created_at__lte=cutoff, date__lte=cutoff.date()).order_by("date").values("patient_id", "date", "scheduled_doses", "taken_doses", "created_at"))
    grouped = []
    for source in (labs, entries, dose_logs):
        by_patient = defaultdict(list)
        for row in source:
            by_patient[row["patient_id"]].append(row)
        grouped.append(by_patient)
    labs_by_patient, entries_by_patient, doses_by_patient = grouped
    reports_by_patient = defaultdict(list)
    for row in reports:
        reports_by_patient[row["patient_id"]].append(row)
    by_id = {row["id"]: row for row in records}

    def root_id(row):
        seen = set()
        while row.get("correction_of_id") in by_id and row["id"] not in seen:
            seen.add(row["id"])
            parent = by_id[row["correction_of_id"]]
            if parent["patient_id"] != row["patient_id"]:
                break
            row = parent
        return row["id"]

    roots, latest = {}, {}
    for row in records:
        root = root_id(row)
        roots[root] = by_id[root]
        latest[root] = row
    historical_events, current_events = {}, {}
    for root, original in roots.items():
        key = (original["patient_id"], original["created_at"].date(), str(root))
        historical_events[key] = {**original, "observed_at": original["created_at"], "available_at": original["created_at"], "source": "record"}
        current_events[key] = {**latest[root], "observed_at": original["created_at"], "available_at": latest[root]["created_at"], "source": "record"}
    for report in reports:
        data = report["extraction"]
        measured = timestamp(data.get("measured_at")) if isinstance(data, dict) else None
        if not isinstance(data, dict) or data.get("status") != "extracted" or data.get("format") not in MONTHLY_FORMATS or measured is None or measured > cutoff:
            continue
        pressure, glucose = data.get("blood_pressure", {}), data.get("blood_sugar", {})
        if pressure.get("unit") != "mmHg":
            continue
        linked = by_id.get(report["record_id"])
        root = root_id(linked) if linked and linked["patient_id"] == report["patient_id"] else None
        original = roots.get(root)
        key = (report["patient_id"], measured.date(), str(root) if original and original["created_at"].date() == measured.date() else "report:" + str(report["id"]))
        vitals = {"systolic": pressure.get("systolic"), "diastolic": pressure.get("diastolic")}
        if glucose.get("unit") == "mg/dL":
            vitals.update(glucose_mg_dl=glucose.get("value"), glucose_context=glucose.get("context"))
        available = max(measured, report["created_at"])
        event = {"patient_id": report["patient_id"], "observed_at": measured, "available_at": available, "created_at": report["created_at"], "vitals": vitals, "diagnosis": latest[root]["diagnosis"] if root in latest else "", "source": "report"}
        existing = current_events.get(key)
        if existing is None or existing["available_at"] <= available:
            # A later authored correction is the current encounter content;
            # an older report must not overwrite it merely because reports are
            # loaded after consultation rows.
            current_events[key] = event
        if available <= measured:
            historical_events[key] = {**event, "diagnosis": original["diagnosis"] if original and original["created_at"] <= measured else ""}
        else:
            # Keep a contemporaneous linked consultation, if one exists. A
            # standalone late upload cannot invent an earlier feature snapshot.
            if key not in historical_events:
                historical_events[key] = event

    def snapshot(event, historical):
        pid, observed = event["patient_id"], event["observed_at"]
        knowledge_at = observed if historical else cutoff
        patient, area = patients[pid], area_by_id.get(pid)
        vitals = event["vitals"] if isinstance(event["vitals"], dict) else {}
        generated_disease_visit = vitals.get("synthetic") is True and vitals.get("generator") == "disease_v1"
        pressure, glucose = blood_pressure(vitals) or {}, blood_sugar(vitals) or {}
        # A lab is usable only after both measurement and recording. Future
        # measurements are never carried backward, even in the current view.
        glucose_candidates = [lab for lab in labs_by_patient[pid] if lab["measured_at"] <= observed and lab["created_at"] <= knowledge_at and (observed - lab["measured_at"]).days <= 90 and lab["unit"].strip().casefold() == "mg/dl" and "glucose" in lab["name"].casefold()]
        if not glucose and glucose_candidates and not generated_disease_visit:
            lab = glucose_candidates[-1]
            glucose = {"value": lab["value"], "context": "fasting" if "fasting" in lab["name"].casefold() else "unknown"}
        active_conditions = [entry for entry in entries_by_patient[pid] if entry["created_at"] <= observed and (not entry["resolved_at"] or entry["resolved_at"] > observed)]
        disease_codes = recognized_diseases(event.get("diagnosis"))
        # A primary label is a target, never a predictor. Legacy visits qualify
        # only when their own diagnosis unambiguously names one supported disease.
        explicit_primary = vitals.get("primary_disease_code")
        valid_primary = isinstance(explicit_primary, str) and explicit_primary in DISEASE_LABELS
        primary_disease = explicit_primary if valid_primary else (next(iter(disease_codes)) if len(disease_codes) == 1 else None)
        if valid_primary:
            disease_codes.add(explicit_primary)
        secondary = vitals.get("secondary_disease_codes", [])
        if isinstance(secondary, list):
            disease_codes.update(code for code in secondary if isinstance(code, str) and code in DISEASE_LABELS)
        for entry in active_conditions:
            disease_codes.update(recognized_diseases(entry["name"]))
        logs = [row for row in doses_by_patient[pid] if observed.date() - timedelta(days=29) <= row["date"] <= observed.date() and row["created_at"] <= knowledge_at]
        if historical:
            # The editable daily table has no last-edited timestamp. Recover
            # historical doses from immutable report payloads instead of assuming
            # a later patient edit was already known at the prediction date.
            historical_days = {}
            for report in reports_by_patient[pid]:
                payload = report["extraction"]
                if not isinstance(payload, dict) or payload.get("status") != "extracted" or report["created_at"] > observed:
                    continue
                measured = timestamp(payload.get("measured_at"))
                if measured is None or measured > observed:
                    continue
                for day in payload.get("adherence", {}).get("daily", []):
                    try:
                        diary_date = datetime.fromisoformat(day["date"]).date()
                        scheduled, taken = day["scheduled_doses"], day["taken_doses"]
                    except (KeyError, ValueError, TypeError):
                        continue
                    if (observed.date() - timedelta(days=29) <= diary_date <= observed.date()
                            and type(scheduled) is int and type(taken) is int and 0 <= taken <= scheduled and scheduled > 0):
                        historical_days[diary_date] = {"scheduled_doses": scheduled, "taken_doses": taken}
            logs = list(historical_days.values())
        scheduled = sum(row["scheduled_doses"] for row in logs)
        taken = sum(row["taken_doses"] for row in logs)
        dob = patient["date_of_birth"]
        age = observed.year - dob.year - ((observed.month, observed.day) < (dob.month, dob.day)) if dob else None
        height, weight = finite(vitals.get("height_cm"), 40, 260), finite(vitals.get("weight_kg"), 10, 600)
        bmi = finite(vitals.get("bmi"), 5, 100)
        if bmi is None and height and weight:
            bmi = finite(weight / (height / 100) ** 2, 5, 100)
        return {
            "patient_key": hmac.new(settings.SECRET_KEY.encode(), (batch.key + ":" + str(pid)).encode(), hashlib.sha256).hexdigest(),
            "observed_at": observed.isoformat(), "available_at": event["available_at"].isoformat(),
            "age": finite(age, 0, 130), "gender": patient["gender"],
            "systolic": finite(vitals.get("systolic") if generated_disease_visit else pressure.get("systolic"), 40, 300),
            "diastolic": finite(vitals.get("diastolic") if generated_disease_visit else pressure.get("diastolic"), 20, 200),
            "glucose": finite(glucose.get("value"), 20, 1000), "glucose_context": glucose.get("context") or "unknown",
            "pulse": finite(vitals.get("pulse", vitals.get("heart_rate_bpm", vitals.get("heart_rate"))), 20, 250),
            "temperature": finite(vitals.get("temperature_c", vitals.get("temperature")), 25, 45),
            "bmi": bmi, "condition_count": len(active_conditions), "adherence": round(100 * taken / scheduled, 6) if scheduled and 0 <= taken <= scheduled else None,
            "disease_codes": sorted(disease_codes or ({"UNKNOWN"} if str(event.get("diagnosis") or "").strip() or active_conditions else {"NO_RECORDED_DISEASE"})),
            "station_id": area.station.key if area else "UNKNOWN", "station_name": area.station.name if area else "Unknown area", "lines": area.station.lines if area else [],
            "latitude": finite(area.latitude, -90, 90) if area else None,
            "longitude": finite(area.longitude, -180, 180) if area else None,
            "station_latitude": area.station.latitude if area else None,
            "station_longitude": area.station.longitude if area else None,
            "age_band": f"{int(age) // 10 * 10}s" if age is not None and age >= 0 else "Unknown",
            "source": event["source"],
            "synthetic": bool(batch.synthetic and (area is not None or vitals.get("synthetic") is True)),
            "primary_disease": primary_disease, "month": observed.month,
            "hemoglobin": finite(vitals.get("hemoglobin"), 2, 25),
            "spo2": finite(vitals.get("spo2"), 50, 100),
            "platelets": finite(vitals.get("platelets"), 5000, 1500000),
            **{flag: (int(vitals["symptoms"][flag]) if isinstance(vitals.get("symptoms"), dict) and type(vitals["symptoms"].get(flag)) in (int, bool) and vitals["symptoms"][flag] in (0, 1) else None) for flag in SYMPTOM_FLAGS},
        }

    selected_codes = selected_disease_codes(filters)
    def selected(events, historical):
        result = []
        for event in events.values():
            if not in_window(event["observed_at"], filters):
                continue
            row = snapshot(event, historical)
            matches_disease = selected_codes is None or bool(selected_codes.intersection(row["disease_codes"]))
            if historical:
                # Keep the private historical snapshots with explicit filter
                # eligibility; disease training consumes only matching visits.
                row["eligible_index"] = bool(matches_disease)
                result.append(row)
            elif matches_disease:
                if selected_codes is not None:
                    row["disease_codes"] = sorted(selected_codes.intersection(row["disease_codes"]))
                result.append(row)
        return sorted(result, key=lambda row: (row["patient_key"], row["observed_at"], row["source"]))

    history, cohort = selected(historical_events, True), selected(current_events, False)
    selected_patients = {row["patient_key"] for row in cohort}
    days = [row["observed_at"][:10] for row in cohort]
    selected_ids = {pid for pid in patients if hmac.new(settings.SECRET_KEY.encode(), (batch.key + ":" + str(pid)).encode(), hashlib.sha256).hexdigest() in selected_patients}
    selected_reports = [row for row in reports if row["patient_id"] in selected_ids and in_window(timestamp((row["extraction"] if isinstance(row["extraction"], dict) else {}).get("measured_at")) or row["created_at"], filters)]
    selected_lab_count = sum(row["selected"] for row in lab_counts if row["patient_id"] in selected_ids)
    selected_doses = [row for row in dose_logs if row["patient_id"] in selected_ids and in_window(datetime.combine(row["date"], time.min, tzinfo=dt_timezone.utc), filters)]
    selected_entries = [row for row in entries if row["patient_id"] in selected_ids and in_window(row["created_at"], filters)]
    selected_extracted = [row for row in selected_reports if isinstance(row["extraction"], dict) and row["extraction"].get("status") == "extracted" and row["extraction"].get("format") in MONTHLY_FORMATS]
    sources = {
        "patients": safe_count(len(selected_patients)), "mapped_patients": safe_count(len(area_by_id)),
        "visits": safe_count(len(cohort)), "reports": safe_count(len(selected_reports)), "labs": safe_count(selected_lab_count),
        "adherence_logs": safe_count(len(selected_doses)), "conditions": safe_count(len(selected_entries)),
        "extracted_reports": safe_count(len(selected_extracted)), "unsupported_reports": safe_count(len(selected_reports) - len(selected_extracted)),
        "historically_unavailable_reports": safe_count(sum((timestamp(row["extraction"].get("measured_at")) or row["created_at"]) < row["created_at"] for row in selected_extracted)),
        "corrections_deduplicated": safe_count(len(records) - len(roots)),
        "history_start": min(days) if days else None, "history_end": max(days) if days else None,
        "cutoff": cutoff.isoformat(), "source_scope": "Clinical rows belonging to the selected patient cohort and measured or recorded within the selected dates. Disease training uses matching visit snapshots with measurements available at that visit.",
        "excluded": {"unmapped_patients": safe_count(0 if include_unmapped else len(unmapped)), "other_dataset_patients": safe_count(other_batch_count), "missing_geography": safe_count(sum(not area_by_id.get(pid) or area_by_id[pid].latitude is None or area_by_id[pid].longitude is None for pid in selected_ids))},
        "unmapped_patients_included": safe_count(len(unmapped) if include_unmapped else 0),
        "historical_adherence_note": "Historical training uses report-backed dose diaries only. Editable patient logs have no edit timestamp, so their earlier values cannot be reconstructed safely.",
        "provenance_note": "Mapped rows belong to the synthetic dataset. Additional unmapped patients are included only in the explicitly selected synthetic database; their geography remains unknown. Data origin must be reviewed before any use beyond this demonstration.",
        "snapshot_sha256": hashlib.sha256(json.dumps({"history": history, "cohort": cohort}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
    }
    return {"history": history, "cohort": cohort, "source": sources}


def summarize_cohort(rows):
    diseases, months, stations = defaultdict(set), defaultdict(set), {}
    station_diseases = defaultdict(lambda: defaultdict(set))
    for row in rows:
        patient = row["patient_key"]
        months[row["observed_at"][:7]].add(patient)
        for code in row["disease_codes"]:
            diseases[code].add(patient)
            station_diseases[row["station_id"]][code].add(patient)
        station = stations.setdefault(row["station_id"], {"station_id": row["station_id"], "station_name": row["station_name"], "lines": row["lines"], "latitude": row["station_latitude"], "longitude": row["station_longitude"], "patients": set()})
        station["patients"].add(patient)
    return {
        "patients": safe_count(len({row["patient_key"] for row in rows})),
        "disease_counts": [{"code": code, "label": ML_DISEASE_LABELS.get(code, code), "count": safe_count(len(group))} for code, group in sorted(diseases.items())],
        "monthly_counts": [{"month": month, "count": safe_count(len(group))} for month, group in sorted(months.items())],
        "stations": [{**{key: value for key, value in row.items() if key != "patients"}, "count": safe_count(len(row["patients"])), "patient_count": safe_count(len(row["patients"]))} for row in sorted(stations.values(), key=lambda row: row["station_name"])],
        "station_disease_counts": [{"station_id": row["station_id"], "station_name": row["station_name"], "patient_count": safe_count(len(row["patients"])), "diseases": [{"code": code, "label": ML_DISEASE_LABELS.get(code, code), "count": safe_count(len(station_diseases[row["station_id"]][code]))} for code in sorted(diseases)]} for row in sorted(stations.values(), key=lambda row: row["station_name"])],
    }
