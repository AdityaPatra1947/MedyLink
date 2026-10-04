"""Deterministic extraction of the documented synthetic monthly PDF format.

No OCR, free-text guessing, diagnosis, or inference from an unsupported report.
The upload and all extracted rows commit together under the caller's transaction.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from pypdf import PdfReader
from rest_framework.exceptions import ValidationError

from .models import LabResult, MedicalReport, MedicationAdherenceLog, Patient
from .report_formats import MONTHLY_BLOCKS, MONTHLY_END, MONTHLY_FORMAT, MONTHLY_START
from .services import approved

FORMAT = MONTHLY_FORMAT
START = MONTHLY_START
END = MONTHLY_END
FIELDS = {
    "Report-ID", "Patient-Account-ID", "Doctor-Account-ID", "Measured-At",
    "Systolic-mmHg", "Diastolic-mmHg", "Fasting-Glucose-mg-dL",
    "Adherence-Period-Start", "Adherence-Period-End",
}
FRIENDLY_FIELDS = {
    "Report ID": "Report-ID", "Patient account ID": "Patient-Account-ID",
    "Doctor account ID": "Doctor-Account-ID", "Measured at": "Measured-At",
    "Systolic (mmHg)": "Systolic-mmHg", "Diastolic (mmHg)": "Diastolic-mmHg",
    "Fasting glucose (mg/dL)": "Fasting-Glucose-mg-dL",
    "Diary starts": "Adherence-Period-Start", "Diary ends": "Adherence-Period-End",
}
MAX_PAGES = 4
MAX_CONTENT_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 50000


def unsupported(reason="This PDF does not use the supported monthly report format."):
    return {"status": "unsupported", "reason": reason}


def _text(file):
    """Bound text processing; malformed/encrypted/nontext PDFs remain downloadable."""
    try:
        file.seek(0)
        reader = PdfReader(file, strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PAGES:
            return None
        pages, total = [], 0
        for page in reader.pages:
            contents = page.get_contents()
            if contents and len(contents.get_data()) > MAX_CONTENT_BYTES:
                return None
            text = page.extract_text() or ""
            total += len(text)
            if total > MAX_TEXT_CHARS:
                return None
            pages.append(text)
        return "\n".join(pages)
    except Exception:  # noqa: BLE001 - untrusted PDF parsing must not expose its content
        return None
    finally:
        file.seek(0)


def _invalid(message):
    raise ValidationError({"file": "Monthly report validation failed: " + message})


def _reading(fields, key, minimum, maximum):
    raw = fields[key]
    if not re.fullmatch(r"[0-9]{1,4}(?:\.[0-9]{1,2})?", raw):
        _invalid(f"{key} must be a numeric reading in the stated units.")
    try:
        number = Decimal(raw)
    except InvalidOperation:
        _invalid(f"{key} must be finite.")
    if not number.is_finite() or not minimum <= number <= maximum:
        _invalid(f"{key} is outside the supported measurement bounds.")
    return float(number)


def parse_monthly_pdf(file, patient, doctor):
    text = _text(file)
    if text is None:
        return unsupported("No supported, bounded text block could be extracted.")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    blocks = [block for block in MONTHLY_BLOCKS if block[0] in lines]
    if not blocks:
        return unsupported()
    if len(blocks) != 1:
        _invalid("exactly one complete measurement block is required.")
    start, end, report_format = blocks[0]
    if (
        sum(lines.count(block[0]) for block in MONTHLY_BLOCKS) != 1
        or sum(lines.count(block[1]) for block in MONTHLY_BLOCKS) != 1
        or lines.count(end) != 1
    ):
        _invalid("exactly one complete measurement block is required.")
    first, last = lines.index(start), lines.index(end)
    fields, daily_lines = {}, []
    for line in lines[first + 1:last]:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\s*\|\s*[0-9]{1,5}\s*\|\s*[0-9]{1,5}", line):
            daily_lines.append(re.sub(r"\s*\|\s*", "|", line))
            continue
        key, delimiter, value = line.partition(":")
        key = FRIENDLY_FIELDS.get(key, key)
        if key == "Dose-Day" and delimiter:
            daily_lines.append(value.strip())
            continue
        if not delimiter or key not in FIELDS or key in fields:
            _invalid("the measurement block has duplicate or unsupported fields.")
        fields[key] = value.strip()
    if first >= last or set(fields) != FIELDS:
        _invalid("all required measurement fields must be present.")
    if fields["Patient-Account-ID"] != patient.user.account_id:
        _invalid("the patient account ID does not match the selected patient.")
    if fields["Doctor-Account-ID"] != doctor.account_id:
        _invalid("the doctor account ID does not match the uploading doctor.")
    if not re.fullmatch(r"(?:ML|AT)-DEMO-PAT[0-9]{4}-[0-9]{6}", fields["Report-ID"]):
        _invalid("the report ID is not a supported monthly report identifier.")
    try:
        measured = parse_datetime(fields["Measured-At"])
    except (ValueError, TypeError):
        measured = None
    if (
        measured is None or timezone.is_naive(measured) or measured > timezone.now()
        or measured.year < 1900
        or (patient.date_of_birth and measured.date() < patient.date_of_birth)
    ):
        _invalid("the measurement date must be a valid past timestamp with a timezone.")
    if not fields["Report-ID"].endswith(measured.strftime("%Y%m")):
        _invalid("the report month does not match the measurement date.")
    try:
        period_start = date.fromisoformat(fields["Adherence-Period-Start"])
        period_end = date.fromisoformat(fields["Adherence-Period-End"])
    except (ValueError, TypeError):
        _invalid("adherence period dates must use YYYY-MM-DD.")
    if (
        not 0 <= (period_end - period_start).days <= 30
        or period_end > measured.date() or period_end > timezone.localdate()
        or (patient.date_of_birth and period_start < patient.date_of_birth)
        or not 1 <= len(daily_lines) <= 31
    ):
        _invalid("adherence requires a valid past period of at most 31 days and daily counts.")
    daily, seen = [], set()
    for line in daily_lines:
        match = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2})\|([0-9]{1,5})\|([0-9]{1,5})", line)
        if not match:
            _invalid("Dose-Day must contain date|scheduled|taken integer counts.")
        try:
            day = date.fromisoformat(match[1])
        except ValueError:
            _invalid("a dose date is invalid.")
        scheduled, taken = int(match[2]), int(match[3])
        if (
            day in seen or not period_start <= day <= period_end
            or not 1 <= scheduled <= 10000 or not 0 <= taken <= scheduled
        ):
            _invalid("dose dates must be unique and in-period, with valid scheduled/taken counts.")
        seen.add(day)
        daily.append({"date": day.isoformat(), "scheduled_doses": scheduled, "taken_doses": taken})
    systolic = _reading(fields, "Systolic-mmHg", 40, 300)
    diastolic = _reading(fields, "Diastolic-mmHg", 20, 200)
    if systolic <= diastolic:
        _invalid("systolic pressure must exceed diastolic pressure.")
    glucose = _reading(fields, "Fasting-Glucose-mg-dL", 20, 1000)
    return {
        "status": "extracted", "format": report_format,
        "report_reference": fields["Report-ID"],
        "measured_at": measured.isoformat(),
        "adherence": {
            "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "days_logged": len(daily), "scheduled_doses": sum(row["scheduled_doses"] for row in daily),
            "taken_doses": sum(row["taken_doses"] for row in daily), "daily": daily,
        },
        "blood_pressure": {"systolic": systolic, "diastolic": diastolic, "unit": "mmHg"},
        "blood_sugar": {"value": glucose, "unit": "mg/dL", "context": "fasting"},
        "source": "Structured monthly PDF", "synthetic": True,
    }


def extract_report_observations(report, file):
    """Reusable by upload and synthetic seeding; caller must own an atomic transaction."""
    if not connection.in_atomic_block:
        raise RuntimeError("Report extraction requires an atomic transaction.")
    # Match clinical lock ordering: provider -> patient -> report.
    doctor = get_user_model().objects.select_for_update().get(pk=report.uploaded_by_id)
    patient = Patient.objects.select_for_update().select_related("user").get(pk=report.patient_id)
    locked = MedicalReport.objects.select_for_update().get(pk=report.pk)
    if isinstance(locked.extraction, dict) and locked.extraction.get("status") == "extracted":
        report.extraction = locked.extraction
        return report.extraction
    if not getattr(settings, "SYNTHETIC_REPORT_EXTRACTION_ALLOWED", False):
        result = unsupported("Synthetic monthly extraction is disabled in this environment.")
    elif locked.content_type != "application/pdf" or doctor.role != "doctor":
        result = unsupported("Automatic extraction supports doctor-uploaded monthly PDFs only.")
    else:
        approved(doctor)
        result = parse_monthly_pdf(file, patient, doctor)
    if result["status"] == "extracted":
        measured = datetime.fromisoformat(result["measured_at"])
        glucose = result["blood_sugar"]
        # Blood pressure is a cuff vital, not a laboratory analyte. Its readings
        # stay in the report extraction used by the dashboard's vital trends.
        LabResult.objects.bulk_create([
            LabResult(
                patient=patient, recorded_by=doctor, report=locked,
                name="Fasting glucose", value=Decimal(str(glucose["value"])),
                unit="mg/dL", measured_at=measured,
                reference_low=Decimal("70"), reference_high=Decimal("99"),
            )
        ])
        MedicationAdherenceLog.objects.bulk_create([
            MedicationAdherenceLog(
                patient=patient, date=date.fromisoformat(row["date"]),
                scheduled_doses=row["scheduled_doses"], taken_doses=row["taken_doses"],
                report=locked,
            ) for row in result["adherence"]["daily"]
        ], update_conflicts=True, unique_fields=["patient", "date"],
            update_fields=["scheduled_doses", "taken_doses", "report"])
    locked.extraction = result
    locked.save(update_fields=["extraction"])
    report.extraction = result
    return result
