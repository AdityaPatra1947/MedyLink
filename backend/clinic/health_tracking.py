"""Observed health data and explicitly configured calculations; no default diagnosis."""

import logging
import math
from datetime import datetime, time, timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.module_loading import import_string

from .models import ClinicalEntry, LabResult, MedicalReport, MedicationAdherenceLog
from .report_formats import MONTHLY_FORMATS

logger = logging.getLogger(__name__)
PERIOD_DAYS = 30
COMPONENT_KEYS = {
    "systolic",
    "diastolic",
    "blood_sugar",
    "adherence",
    "abnormal_labs",
    "conditions",
}


def adherence_data(patient):
    today = timezone.localdate()
    rows = list(
        MedicationAdherenceLog.objects.filter(
            patient=patient,
            date__gte=today - timedelta(days=PERIOD_DAYS - 1),
            date__lte=today,
        ).order_by("-date")
    )
    scheduled = sum(row.scheduled_doses for row in rows)
    taken = sum(row.taken_doses for row in rows)
    summary = (
        None
        if not scheduled
        else {
            "percentage": round(taken / scheduled * 100, 1),
            "scheduled_doses": scheduled,
            "taken_doses": taken,
            "days_logged": len(rows),
            "period_days": PERIOD_DAYS,
            "period_start": (today - timedelta(days=PERIOD_DAYS - 1)).isoformat(),
            "period_end": today.isoformat(),
            "missing_days": PERIOD_DAYS - len(rows),
            "formula": "Adherence (%) = taken doses / scheduled doses x 100",
            "explanation": (
                "Totals use only logged scheduled and taken doses in the last 30 days. "
                "Unlogged days are unknown, not automatically missed doses. "
                "Blood pressure, glucose and pharmacy dispensing do not determine adherence."
            ),
            "source": "dose_logs",
            "report_ids": sorted({str(row.report_id) for row in rows if row.report_id}),
            "report_days": sum(row.report_id is not None for row in rows),
            "self_reported_days": sum(row.report_id is None for row in rows),
        }
    )
    return {
        "results": [
            {
                "id": str(row.id),
                "date": row.date.isoformat(),
                "scheduled_doses": row.scheduled_doses,
                "taken_doses": row.taken_doses,
                "report_id": str(row.report_id) if row.report_id else None,
                "source": "monthly_report" if row.report_id else "patient_log",
            }
            for row in rows
        ],
        "summary": summary,
    }


def lab_flag(result):
    if result.reference_low is not None and result.value < result.reference_low:
        return "low"
    if result.reference_high is not None and result.value > result.reference_high:
        return "high"
    if result.reference_low is None and result.reference_high is None:
        return "unknown"
    return "normal"


def lab_payload(result):
    return {
        "id": str(result.id),
        "name": result.name,
        "value": float(result.value),
        "unit": result.unit,
        "reference_low": float(result.reference_low)
        if result.reference_low is not None
        else None,
        "reference_high": float(result.reference_high)
        if result.reference_high is not None
        else None,
        "flag": lab_flag(result),
        "measured_at": result.measured_at.isoformat(),
        "recorded_by_name": result.recorded_by.name,
        "source": result.recorded_by.role,
        "report_id": str(result.report_id) if result.report_id else None,
    }


def latest_labs(patient):
    latest = {}
    for row in (
        LabResult.objects.filter(patient=patient)
        .order_by("-measured_at", "-created_at", "-id")
        .iterator(chunk_size=100)
    ):
        key = (row.name.strip().casefold(), row.unit.strip())
        latest.setdefault(key, row)
    return list(latest.values())


def lab_summary(results):
    comparable = [row for row in results if lab_flag(row) != "unknown"]
    return {
        "abnormal": sum(lab_flag(row) in ("high", "low") for row in comparable)
        if comparable
        else None,
        "total": len(results) if results else None,
    }


def _number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _validate_policy(policy):
    if not isinstance(policy, dict):
        return False
    if any(
        not isinstance(policy.get(key), str)
        or not policy[key].strip()
        or len(policy[key]) > 120
        for key in ("method", "version", "label")
    ):
        return False
    components, bands = policy.get("components"), policy.get("risk_bands")
    if not isinstance(components, list) or not 1 <= len(components) <= len(
        COMPONENT_KEYS
    ):
        return False
    seen = set()
    for component in components:
        if (
            not isinstance(component, dict)
            or component.get("key") not in COMPONENT_KEYS
            or component["key"] in seen
        ):
            return False
        seen.add(component["key"])
        if (
            not isinstance(component.get("label"), str)
            or not component["label"].strip()
        ):
            return False
        if (
            not _number(component.get("weight"))
            or component["weight"] <= 0
            or component["weight"] > 1000000
        ):
            return False
        if (
            type(component.get("max_age_days")) is not int
            or not 1 <= component["max_age_days"] <= 3650
        ):
            return False
        if "min_days_logged" in component and (
            component["key"] != "adherence"
            or type(component["min_days_logged"]) is not int
            or not 1 <= component["min_days_logged"] <= PERIOD_DAYS
        ):
            return False
        rules = component.get("rules")
        if not isinstance(rules, list) or not 1 <= len(rules) <= 100:
            return False
        previous = -math.inf
        for index, rule in enumerate(rules):
            if (
                not isinstance(rule, dict)
                or "upper_bound" not in rule
                or not _number(rule.get("score"))
                or not 0 <= rule["score"] <= 100
            ):
                return False
            bound = rule["upper_bound"]
            if index == len(rules) - 1:
                if bound is not None:
                    return False
            elif not _number(bound) or bound <= previous:
                return False
            else:
                previous = bound
    if not isinstance(bands, list) or not 1 <= len(bands) <= 20:
        return False
    seen = set()
    for band in bands:
        if (
            not isinstance(band, dict)
            or not _number(band.get("min_score"))
            or not 0 <= band["min_score"] <= 100
            or band["min_score"] in seen
        ):
            return False
        if (
            not isinstance(band.get("label"), str)
            or not band["label"].strip()
            or len(band["label"]) > 120
        ):
            return False
        seen.add(band["min_score"])
    return 0 in seen


def _policy_valid(policy):
    try:
        return _validate_policy(policy)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _timestamp(value):
    if isinstance(value, str):
        try:
            value = parse_datetime(value)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, datetime):
        return None
    return timezone.make_aware(value) if timezone.is_naive(value) else value


def _score(patient, trends, conditions, adherence, labs):
    policy = getattr(settings, "HEALTH_SCORE_POLICY", None)
    if policy is None:
        return None, None, "A health score calculation policy has not been configured."
    if not _policy_valid(policy):
        logger.warning("Health score policy configuration is invalid.")
        return (
            None,
            None,
            "The configured health score calculation policy is unavailable.",
        )
    now, components = timezone.now(), []
    for component in policy["components"]:
        key, value, measured_at = component["key"], None, None
        if key in ("systolic", "diastolic", "blood_sugar"):
            points = trends.get(
                "blood_sugar" if key == "blood_sugar" else "blood_pressure", []
            )
            if points:
                row = points[-1]
                value = row.get("value" if key == "blood_sugar" else key)
                measured_at = _timestamp(row.get("recorded_at"))
        elif key == "adherence" and adherence["summary"]:
            if adherence["summary"]["days_logged"] >= component.get(
                "min_days_logged", 1
            ):
                value = adherence["summary"]["percentage"]
                # Daily self reports are dated observations, not an inference from dispensing.
                measured_at = timezone.make_aware(
                    datetime.combine(
                        datetime.fromisoformat(adherence["results"][0]["date"]).date(),
                        time.min,
                    )
                )
        elif (
            key == "abnormal_labs"
            and labs
            and all(lab_flag(row) != "unknown" for row in labs)
        ):
            value = lab_summary(labs)["abnormal"]
            measured_at = min(row.measured_at for row in labs)
        elif key == "conditions":
            rows = list(
                ClinicalEntry.objects.filter(patient=patient, kind="condition").values(
                    "created_at", "resolved_at"
                )
            )
            active_dates = [
                row["created_at"] for row in rows if row["resolved_at"] is None
            ]
            resolved_dates = [
                row["resolved_at"] for row in rows if row["resolved_at"] is not None
            ]
            if active_dates or resolved_dates:
                value = conditions
                measured_at = min(active_dates) if active_dates else max(resolved_dates)
        if not _number(value) or measured_at is None:
            return None, None, f"Required data is missing for {component['label']}."
        if measured_at > now or measured_at < now - timedelta(
            days=component["max_age_days"]
        ):
            return (
                None,
                None,
                f"A recent observation is required for {component['label']}.",
            )
        rule = next(
            rule
            for rule in component["rules"]
            if rule["upper_bound"] is None or value <= rule["upper_bound"]
        )
        components.append(
            {
                "key": key,
                "label": component["label"],
                "value": value,
                "score": rule["score"],
                "weight": component["weight"],
            }
        )
    value = round(
        sum(row["score"] * row["weight"] for row in components)
        / sum(row["weight"] for row in components)
    )
    band = next(
        band
        for band in sorted(
            policy["risk_bands"], key=lambda item: item["min_score"], reverse=True
        )
        if value >= band["min_score"]
    )
    return (
        {
            "value": value,
            "label": policy["label"],
            "method": f"{policy['method']} ({policy['version']})",
            "calculated_at": now.isoformat(),
            "components": components,
        },
        band["label"],
        "",
    )



SYNTHETIC_RULES = {
    "systolic": [(90, 40), (120, 100), (130, 85), (140, 70), (160, 50), (None, 25)],
    "diastolic": [(60, 40), (80, 100), (90, 70), (100, 50), (None, 25)],
    "blood_sugar": [(70, 30), (100, 100), (126, 70), (180, 40), (None, 20)],
}
SYNTHETIC_RULE_TEXT = {
    "systolic": "<90: 40; 90-119: 100; 120-129: 85; 130-139: 70; 140-159: 50; >=160: 25",
    "diastolic": "<60: 40; 60-79: 100; 80-89: 70; 90-99: 50; >=100: 25",
    "blood_sugar": "<70: 30; 70-99: 100; 100-125: 70; 126-179: 40; >=180: 20",
}


def _synthetic_score(patient, adherence):
    """An explicit demo index from one supported report, never a clinical risk score."""
    reports = []
    for report in MedicalReport.objects.filter(
        patient=patient, extraction__status="extracted", extraction__format__in=MONTHLY_FORMATS,
    ).iterator(chunk_size=64):
        measured = _timestamp(report.extraction.get("measured_at"))
        if measured is not None and measured <= timezone.now():
            reports.append((measured, str(report.id), report))
    if not reports:
        return None, None, "A supported monthly PDF report is required for the demo score."
    measured, _, report = max(reports, key=lambda row: (row[0], row[1]))
    if measured < timezone.now() - timedelta(days=45):
        return None, None, "A monthly PDF report measured within the last 45 days is required."
    summary = adherence["summary"]
    if not summary or summary["days_logged"] < 7:
        return None, None, "At least 7 days of scheduled and taken dose counts in the last 30 days are required."
    data = report.extraction
    pressure, glucose = data.get("blood_pressure", {}), data.get("blood_sugar", {})
    if pressure.get("unit") != "mmHg" or glucose.get("unit") != "mg/dL" or glucose.get("context") != "fasting":
        return None, None, "The report requires blood pressure and fasting glucose in supported units."
    components = []
    for key, label, value, weight, unit in [
        ("systolic", "Systolic pressure", pressure.get("systolic"), 0.30, "mmHg"),
        ("diastolic", "Diastolic pressure", pressure.get("diastolic"), 0.20, "mmHg"),
        ("blood_sugar", "Fasting glucose", glucose.get("value"), 0.30, "mg/dL"),
    ]:
        if not _number(value):
            return None, None, "The monthly report is missing a required numeric measurement."
        score = next(score for upper, score in SYNTHETIC_RULES[key] if upper is None or value < upper)
        components.append({
            "key": key, "label": label, "value": value, "score": score, "weight": weight,
            "unit": unit, "formula": SYNTHETIC_RULE_TEXT[key],
            "explanation": "Demo point bands; they do not diagnose disease or determine treatment.",
            "rules": [{"upper_bound_exclusive": upper, "score": points} for upper, points in SYNTHETIC_RULES[key]],
            "measured_at": measured.isoformat(), "source_report_id": str(report.id),
            "source_report_title": report.title or report.name, "source": "monthly_report",
        })
    raw_adherence = summary["taken_doses"] / summary["scheduled_doses"] * 100
    components.append({
        "key": "adherence", "label": "Medication adherence", "value": raw_adherence,
        "score": raw_adherence, "weight": 0.20, "unit": "%",
        "formula": f"{summary['taken_doses']} / {summary['scheduled_doses']} x 100 = {raw_adherence:.2f}%",
        "explanation": summary["explanation"], "rules": [],
        "measured_at": adherence["results"][0]["date"], "source": "dose_logs",
        "source_report_id": summary["report_ids"][0] if len(summary["report_ids"]) == 1 else None,
        "source_report_title": "30-day dose log", "source_report_ids": summary["report_ids"],
    })
    # Conventional half-up rounding, matching the visible formula and browser.
    value = math.floor(sum(row["score"] * row["weight"] for row in components) + 0.5)
    return {
        "value": value, "label": "Demo health score", "method": "synthetic-bp-glucose-v1",
        "calculated_at": timezone.now().isoformat(), "components": components,
        "formula": "round(0.30 x systolic points + 0.20 x diastolic points + 0.30 x fasting glucose points + 0.20 x adherence %)",
        "explanation": "Uses the latest supported monthly report (no older than 45 days) and at least 7 logged days in the last 30 days. The weights and point bands are illustrative.",
        "disclaimer": "Synthetic demonstration only. This index is not clinically validated and is not a diagnosis, clinical risk estimate or treatment recommendation.",
    }, None, ""

def regional_alerts(patient):
    unavailable = {"available": False, "items": []}
    provider = getattr(settings, "HEALTH_ALERTS_PROVIDER", "")
    if not provider:
        return unavailable
    try:
        result = import_string(provider)(patient)
        if (
            not isinstance(result, dict)
            or type(result.get("available")) is not bool
            or not isinstance(result.get("items"), list)
        ):
            raise ValueError("Invalid provider result")
        if not result["available"]:
            return unavailable
        items = []
        for item in result["items"][:50]:
            if not isinstance(item, dict):
                raise TypeError("Invalid alert")
            cleaned = {}
            for key, length in {
                "id": 200,
                "title": 200,
                "description": 2000,
                "region": 200,
                "source_url": 2000,
            }.items():
                value = item.get(key)
                if (
                    not isinstance(value, str)
                    or not value.strip()
                    or len(value) > length
                ):
                    raise ValueError("Invalid alert field")
                cleaned[key] = value.strip()
            parsed = urlsplit(cleaned["source_url"])
            if (
                parsed.scheme not in ("https", "http")
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Invalid source URL")
            published = _timestamp(item.get("published_at"))
            if published is None:
                raise ValueError("Missing publication time")
            cleaned["published_at"] = published.isoformat()
            items.append(cleaned)
        return {"available": True, "items": items}
    except Exception:  # noqa: BLE001 - external adapter failures must not expose patient data
        # The adapter may see a patient; never include its exception or data in logs.
        logger.warning("Regional health alert provider is unavailable.")
        return unavailable


def health_metrics(patient, trends, conditions):
    adherence = adherence_data(patient)
    labs = latest_labs(patient)
    if getattr(settings, "SYNTHETIC_REPORT_SCORE_ENABLED", False):
        score, risk, reason = _synthetic_score(patient, adherence)
    else:
        score, risk, reason = _score(patient, trends, conditions, adherence, labs)
    return {
        "adherence": adherence["summary"],
        "lab_summary": lab_summary(labs),
        "health_score": score,
        "health_score_reason": reason,
        "risk_level": risk,
        "regional_alerts": regional_alerts(patient),
    }
