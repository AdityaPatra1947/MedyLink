"""Reproducible fictional follow-up visits and two-page monthly PDF reports.

The printed observation block is the import source. No dashboard observation is
written directly by this module. Medication examples are synthetic fixtures.
"""

import calendar
import hashlib
import io
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted,
)

from .report_formats import MONTHLY_END, MONTHLY_START

VERSION = "monthly-demo-v1"
NAMESPACE = uuid.UUID("9919a6d8-8873-4c2a-9ae6-4e04dbb8f552")
IST = timezone(timedelta(hours=5, minutes=30))
TEAL = colors.HexColor("#156858")
INK = colors.HexColor("#183f42")
GRAY = colors.HexColor("#57716f")
PALE = colors.HexColor("#f0f6f3")


def stable_id(kind, source_id, month=""):
    return uuid.uuid5(NAMESPACE, f"{VERSION}:{kind}:{source_id}:{month}")


def durations():
    months = [6, 12, 24, 6, 12]
    random.Random(9302026).shuffle(months)
    return months


def monthly_dates(as_of, count):
    number = as_of.year * 12 + as_of.month - 1
    result = []
    for offset in reversed(range(count)):
        year, month = divmod(number - offset, 12)
        month += 1
        result.append(as_of if offset == 0 else date(year, month, calendar.monthrange(year, month)[1]))
    return result


def visit_data(index, source_id, day, month_index, month_count):
    rng = random.Random(f"{VERSION}:{source_id}:{day.isoformat()}")
    targets = [(116, 74, 92), (132, 84, 108), (146, 92, 156), (124, 78, 118), (138, 86, 136)]
    progress = (month_count - month_index - 1) / max(1, month_count - 1)
    target = targets[index]
    jitter = [rng.randint(-2, 2), rng.randint(-1, 1), rng.randint(-3, 3)] if progress else [0, 0, 0]
    systolic, diastolic, glucose = [round(base + progress * rise + variation) for base, rise, variation in zip(target, [16, 8, 25], jitter)]
    diabetes = index in {0, 2, 4}
    symptoms = (
        "Routine follow-up. No current headache, dizziness, chest discomfort or increased thirst. "
        "Home monitoring diary and regular medicines reviewed."
        if month_index == month_count - 1 and index in {0, 3}
        else [
            "Intermittent mild morning headache and fatigue after work; no chest pain, breathlessness or fainting.",
            "Occasional tiredness after meals; no excessive thirst, increased urination, dizziness or chest pain.",
            "Increased thirst and fatigue on some evenings; no vomiting, blurred vision, chest pain or acute illness.",
            "Occasional light headache after a busy day; no syncope, chest discomfort or shortness of breath.",
            "Persistent mild fatigue with occasional increased thirst; no acute pain, fever or recent weight loss.",
        ][index]
    )
    diagnosis = "Essential hypertension; " + ("type 2 diabetes mellitus (established diagnosis)" if diabetes else "impaired fasting glucose under follow-up")
    medicines = [{
        "medicine": "Amlodipine 5 mg tablet", "dosage": "One tablet once daily",
        "instructions": "Fictional maintenance regimen: take at the same time each day; review tolerance at follow-up.",
        "quantity": 30, "unit": "tablet", "daily_doses": 1,
    }]
    if diabetes:
        medicines.append({
            "medicine": "Metformin 500 mg tablet", "dosage": "One tablet twice daily with meals",
            "instructions": "Fictional established regimen: with breakfast and the evening meal; review gastrointestinal tolerance and renal monitoring.",
            "quantity": 60, "unit": "tablet", "daily_doses": 2,
        })
    scheduled = sum(item["daily_doses"] for item in medicines)
    probability = [0.95, 0.86, 0.78, 0.98, 0.90][index]
    daily = [{"date": date(day.year, day.month, d).isoformat(), "scheduled_doses": scheduled,
              "taken_doses": sum(rng.random() < probability for _ in range(scheduled))}
             for d in range(1, day.day + 1)]
    notes = (
        "SYNTHETIC TRAINING RECORD - not a clinical recommendation.\n\n"
        f"History: {symptoms} Known hypertension; "
        + ("established type 2 diabetes on maintenance oral treatment." if diabetes else "prior impaired fasting glucose managed with lifestyle follow-up.")
        + " No reported acute infection. Medication diary reviewed; dose counts are patient-reported and are not inferred from test results.\n\n"
        f"Examination: alert and comfortable, seated after five minutes of rest. Two left-arm automated cuff readings averaged {systolic}/{diastolic} mmHg. "
        f"Pulse {68 + index * 3 + month_index % 5}/min, regular. Fasting serum glucose {glucose} mg/dL after an eight-hour fast. "
        "The attached monthly report contains the individual readings and specimen details.\n\n"
        f"Assessment: {diagnosis}. Measurements reviewed in the context of the recorded history; a single result does not establish a new diagnosis.\n\n"
        "Medication reconciliation: existing maintenance medicines continued in this fictional visit; directions and quantities appear in the linked prescription. "
        "Missed doses discussed without assuming the unlogged days were missed.\n\n"
        "Plan: continue home BP and medication diary; discuss regular meals, activity and salt intake at follow-up. "
        "Repeat fasting glucose and BP next month. Review kidney function and HbA1c through the treating clinician when due. "
        "Return earlier for new or worsening symptoms."
    )
    return {
        "source_id": source_id, "date": day, "measured_at": datetime.combine(day, datetime.min.time().replace(hour=9), tzinfo=IST),
        "systolic": systolic, "diastolic": diastolic, "glucose": glucose,
        "pulse": 68 + index * 3 + month_index % 5, "complaint": symptoms,
        "diagnosis": diagnosis, "notes": notes, "medicines": medicines, "daily": daily,
        "report_reference": f"ML-DEMO-{source_id}-{day:%Y%m}",
    }


def render_report(patient, doctor, application, visit):
    """Return an original A4 PDF layout; no third-party branding or signature."""
    output = io.BytesIO()
    styles = {
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=8.2, leading=11.6, textColor=INK, spaceAfter=4),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.2, leading=10, textColor=GRAY, spaceAfter=3),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=TEAL, spaceBefore=8, spaceAfter=5),
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=INK, spaceAfter=5),
        "mono": ParagraphStyle("mono", fontName="Courier", fontSize=8.3, leading=12.5, textColor=INK),
        "alert": ParagraphStyle("alert", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=TEAL, alignment=TA_CENTER),
    }
    def p(text, style="body"):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])
    def table(rows, widths, header=False):
        cells = [[p(item) for item in row] for row in rows]
        grid = Table(cells, colWidths=widths, hAlign="LEFT")
        commands = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9e5df")),
        ]
        if header:
            commands.append(("BACKGROUND", (0, 0), (-1, 0), PALE))
        grid.setStyle(TableStyle(commands))
        return grid
    def footer(canvas, doc):
        canvas.saveState()
        width, height = doc.pagesize
        canvas.setStrokeColor(TEAL)
        canvas.setLineWidth(3)
        canvas.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
        canvas.setStrokeColor(colors.HexColor("#d9e5df"))
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 18 * mm, width - 18 * mm, 18 * mm)
        canvas.setFillColor(GRAY)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 13 * mm, "SYNTHETIC DEMO - NOT FOR CLINICAL USE")
        canvas.drawRightString(width - 18 * mm, 13 * mm, f"{visit['report_reference']}  |  Page {doc.page}")
        canvas.restoreState()
    day = visit["date"]
    age = day.year - patient.date_of_birth.year - ((day.month, day.day) < (patient.date_of_birth.month, patient.date_of_birth.day))
    width = 174 * mm
    document = SimpleDocTemplate(output, pagesize=(210 * mm, 297 * mm), rightMargin=18 * mm, leftMargin=18 * mm,
                                 topMargin=20 * mm, bottomMargin=23 * mm,
                                 title=f"{patient.user.name} - monthly BP and fasting glucose - {day:%B %Y}",
                                 author="MedyLink synthetic demonstration", pageCompression=1, invariant=1)
    story = [p("MEDYLINK  /  MONTHLY FOLLOW-UP", "small"), p("Blood pressure & fasting glucose", "title"),
             p(f"Report {visit['report_reference']}  |  Visit: {day:%d %B %Y}, 09:00 IST", "small"), Spacer(1, 5)]
    story.append(table([
        [f"PATIENT\n{patient.user.name}\nAccount {patient.user.account_id} | {patient.health_id}", f"DOB / AGE / SEX\n{patient.date_of_birth:%d %b %Y} | {age} years | {patient.gender.title()}\nBlood group: {patient.blood_group}"],
        [f"REFERRING / REVIEWING DOCTOR\n{doctor.name} | {doctor.account_id}\n{application.registration_number}", f"PRACTICE\n{application.practice_address}\nGeneral practice - fictional demonstration"],
    ], [width * 0.53, width * 0.47]))
    story.extend([p("01  Measurement and specimen details", "h"),
        p(f"BP: seated for five minutes, left arm, automated upper-arm cuff; two readings one minute apart. Pulse {visit['pulse']}/min, regular. "
          f"Glucose: serum, fasting for eight hours; enzymatic method. Specimen {visit['source_id']}-{day:%Y%m}-GLU. "
          f"Collected {day:%d %b %Y} 08:15, received 08:35, reported 09:00 IST. All observations and specimen events are simulated.", "small"),
        table([
            ["Measurement", "Result", "Units", "Reference / indicator"],
            ["BP reading 1", f"{visit['systolic']-2}/{visit['diastolic']-1}", "mmHg", "Individual cuff reading"],
            ["BP reading 2", f"{visit['systolic']+2}/{visit['diastolic']+1}", "mmHg", "Individual cuff reading"],
            ["Average systolic / diastolic", f"{visit['systolic']}/{visit['diastolic']}", "mmHg", "Desirable adult: <120 / <80"],
            ["Fasting serum glucose", str(visit["glucose"]), "mg/dL", "70-99; " + ("above reference" if visit["glucose"] > 99 else "within reference")],
        ], [width * 0.34, width * 0.16, width * 0.13, width * 0.37], header=True),
        p("02  Clinical review", "h"), p("Symptoms: " + visit["complaint"]), p("Recorded diagnoses: " + visit["diagnosis"] + "."),
        p("Clinical context: established history reviewed; no diagnosis is inferred automatically from this PDF. Single measurements require clinical interpretation.", "small"),
        p("03  Maintenance prescription and follow-up", "h"),
        table([["Medicine", "Directions", "Quantity"]] + [[item["medicine"], item["dosage"], str(item["quantity"]) + " tablets"] for item in visit["medicines"]],
              [width * 0.39, width * 0.43, width * 0.18], header=True),
        p("Fictional existing regimen only. Follow-up: repeat BP and fasting glucose in one month; bring home BP and medication diary. "
          "Discuss medicine tolerance, routine kidney-function/HbA1c monitoring and lifestyle measures with the treating clinician.", "small"),
        p(f"Recorded by {doctor.name}. Electronic attribution for a demo record; no real clinician signature or laboratory accreditation is claimed.", "small"),
        PageBreak(), p("Medication diary & observation source", "title"),
        p(f"{patient.user.name} | {patient.user.account_id} | {day:%B %Y}", "small"),
        p("Patient-reported dose diary", "h"),
        p("The entries below record scheduled and taken doses for each day. They are fictional self-reported observations reviewed with the named doctor. "
          "Adherence = taken doses / scheduled doses x 100. Missing days remain unknown. Glucose or BP results cannot establish whether medicines were taken."),
        p(f"This report: {sum(row['taken_doses'] for row in visit['daily'])} of {sum(row['scheduled_doses'] for row in visit['daily'])} scheduled doses; "
          f"{len(visit['daily'])} recorded days. The dashboard uses only the most recent 30 calendar days, so its window may differ.", "small"),
        p("Observation details and daily medicine counts", "h"),
        p("Left: report observations. Right: date | scheduled doses | taken doses. Each row represents one recorded day.", "small"),
    ])
    observations = [f"Report ID: {visit['report_reference']}", f"Patient account ID: {patient.user.account_id}",
                    f"Doctor account ID: {doctor.account_id}", f"Measured at: {visit['measured_at'].isoformat()}",
                    f"Systolic (mmHg): {visit['systolic']}", f"Diastolic (mmHg): {visit['diastolic']}",
                    f"Fasting glucose (mg/dL): {visit['glucose']}",
                    f"Diary starts: {day.replace(day=1).isoformat()}", f"Diary ends: {day.isoformat()}"]
    diary = [f"{row['date']} | {row['scheduled_doses']:>3} | {row['taken_doses']:>3}" for row in visit["daily"]]
    diary_table = Table([[Preformatted("\n\n".join(observations), styles["mono"]),
                          Preformatted("\n".join(diary), styles["mono"])]], colWidths=[width * .57, width * .43])
    diary_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, 0), PALE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d9e5df")),
    ]))
    story.extend([p(MONTHLY_START, "small"), diary_table,
                  p(MONTHLY_END, "small"), Spacer(1, 10),
                  p("Format references", "h"),
                  p("Original demo layout informed by the American Heart Association blood pressure log and Labcorp glucose sample-report fields. "
                    "BP is a cuff measurement; serum glucose is a laboratory measurement. These organizations did not issue or approve this report.", "small"),
                  p("heart.org: My Blood Pressure Log | labcorp.com/tests/001032/glucose", "small")])
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def pdf_digest(data):
    return hashlib.sha256(data).hexdigest()
