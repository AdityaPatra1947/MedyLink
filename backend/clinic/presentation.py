import base64
import hashlib
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import qrcode
from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .models import ClinicalEntry
from .services import totals


def profile(p):
    return dict(
        id=str(p.id),
        account_id=p.user.account_id,
        name=p.user.name,
        health_id=p.health_id,
        date_of_birth=p.date_of_birth,
        gender=p.gender,
        phone=p.phone,
        address=p.address,
        blood_group=p.blood_group,
        emergency_contact=p.emergency_contact,
        allergy_status=p.allergy_status,
        photo_url=photo_url(p),
    )


def document(doc):
    return dict(
        id=str(doc.id),
        name=doc.name,
        status=doc.status,
        kind=doc.kind,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
    )


def application(app):
    fields = [
        "version",
        "status",
        "registration_number",
        "registering_body",
        "specialty",
        "qualification",
        "clinic_name",
        "years_experience",
        "opening_hours",
        "practice_address",
        "shop_name",
        "shop_license",
        "shop_license_expires",
        "contact_phone",
        "reason",
        "evidence_reviewed",
        "valid_until",
        "reviewed_at",
        "created_at",
        "is_current",
    ]
    reviews = [
        dict(
            decision=r.decision,
            reason=r.reason,
            evidence_reviewed=r.evidence_reviewed,
            valid_until=r.valid_until,
            reviewer_name=r.reviewer.name,
            created_at=r.created_at,
        )
        for r in sorted(
            app.reviews.all(), key=lambda review: review.created_at, reverse=True
        )[:50]
    ]
    return dict(
        id=str(app.id),
        provider_id=str(app.provider_id),
        provider_account_id=app.provider.account_id,
        name=app.provider.name,
        email=app.provider.email,
        provider_email=app.provider.email,
        email_verified=app.provider.email_verified,
        role=app.provider.role,
        documents=[document(d) for d in app.documents.all()],
        reviews=reviews,
        **{f: getattr(app, f) for f in fields},
    )


def access_request(req, user):
    return dict(
        id=str(req.id),
        patient_id=str(req.patient_id)
        if user.role == "patient" or req.status == "approved"
        else None,
        provider_id=str(req.provider_id),
        provider_name=req.provider.name,
        shop_name=req.application.shop_name,
        scope=req.scope,
        purpose=req.purpose,
        status=req.status,
        created_at=req.created_at,
    )


def grant(g):
    return dict(
        id=str(g.id),
        patient_id=str(g.patient_id),
        provider_id=str(g.provider_id),
        provider_name=g.provider.name,
        shop_name=g.application.shop_name,
        scope=g.scope,
        prescription_id=str(g.prescription_id) if g.prescription_id else None,
        expires_at=g.expires_at,
        revoked_at=g.revoked_at,
    )


def record(r):
    return dict(
        id=str(r.id),
        patient_id=str(r.patient_id),
        doctor_id=str(r.doctor_id),
        doctor_account_id=r.doctor.account_id,
        doctor_name=r.doctor.name,
        complaint=r.complaint,
        diagnosis=r.diagnosis,
        notes=r.notes,
        vitals=r.vitals,
        created_at=r.created_at,
        correction_of=str(r.correction_of_id) if r.correction_of_id else None,
        correction_reason=r.correction_reason,
    )


def entry(e):
    return dict(
        id=str(e.id),
        name=e.name,
        notes=e.notes,
        source=e.source,
        author_id=str(e.author_id),
        author_name=e.author.name,
        created_at=e.created_at,
        resolved_at=e.resolved_at,
        resolution_reason=e.resolution_reason,
    )


def prescription(rx, *, clinical=True):
    items = []
    for item in rx.items.all():
        dispensed = getattr(item, "dispensed_total", None)
        if dispensed is None:
            dispensed = totals(item)
        items.append(
            dict(
                id=str(item.id),
                medicine=item.medicine,
                dosage=item.dosage,
                instructions=item.instructions,
                quantity=str(item.quantity),
                unit=item.unit,
                dispensed=str(dispensed),
                remaining=str(item.quantity - dispensed),
            )
        )
    status = "issued"
    if items and all(DecimalItem(i["remaining"]) == 0 for i in items):
        status = "fulfilled"
    elif any(DecimalItem(i["dispensed"]) > 0 for i in items):
        status = "partially_dispensed"
    if rx.valid_until <= timezone.now():
        status = "expired"
    if rx.cancelled_at:
        status = "cancelled"
    allergies = getattr(rx.patient, "active_allergies", None)
    if allergies is None:
        allergies = ClinicalEntry.objects.filter(
            patient=rx.patient, kind="allergy", resolved_at__isnull=True,
        ).select_related("author").order_by("-created_at")[:100]
    return dict(
        id=str(rx.id),
        patient=dict(
            id=str(rx.patient_id),
            account_id=rx.patient.user.account_id,
            name=rx.patient.user.name,
            health_id=rx.patient.health_id,
            date_of_birth=rx.patient.date_of_birth,
        ),
        **(
            {"record_id": str(rx.record_id) if rx.record_id else None}
            if clinical
            else {}
        ),
        doctor_id=str(rx.doctor_id),
        doctor_account_id=rx.doctor.account_id,
        doctor_name=rx.doctor.name,
        doctor_registration=rx.application.registration_number,
        created_at=rx.created_at,
        valid_until=rx.valid_until,
        status=status,
        notes=rx.notes,
        items=items,
        allergy_status=rx.patient.allergy_status,
        allergies=[entry(e) for e in allergies],
        cancelled_at=rx.cancelled_at,
        cancellation_reason=rx.cancellation_reason,
    )


def DecimalItem(value):
    from decimal import Decimal

    return Decimal(value)


def dispense_event(event):
    return dict(
        id=str(event.id),
        prescription_id=str(event.prescription_id),
        pharmacist_name=event.pharmacist_name,
        shop_name=event.shop_name,
        patient_name=event.patient_name,
        patient_health_id=event.patient_health_id,
        created_at=event.created_at,
        items=[
            dict(medicine=item.medicine, quantity=str(item.quantity), unit=item.unit)
            for item in event.items.all()
        ],
    )


def audit_event(event):
    return dict(
        id=str(event.id),
        event=event.event,
        outcome=event.outcome,
        actor_name=event.actor.name if event.actor else "Anonymous",
        created_at=event.created_at,
        request_id=event.request_id,
    )


def qr_bytes(locator):
    buffer = BytesIO()
    qrcode.make(settings.FRONTEND_ORIGIN.rstrip("/") + "/health-card/" + locator).save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def card(patient):
    return dict(
        patient_id=str(patient.id),
        account_id=patient.user.account_id,
        date_of_birth=patient.date_of_birth,
        blood_group=patient.blood_group,
        photo_url=photo_url(patient),
        health_id=patient.health_id,
        name=patient.user.name,
        locator=patient.card_locator,
        qr_data_url="data:image/png;base64,"
        + base64.b64encode(qr_bytes(patient.card_locator)).decode(),
    )


def card_pdf(patient):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(540, 340))
    pdf.setTitle("MedyLink Health Card")
    pdf.setFillColor(colors.HexColor("#f6faf8"))
    pdf.rect(0, 0, 540, 340, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#12594b"))
    pdf.rect(0, 263, 540, 77, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(26, 299, "MedyLink")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(27, 280, "PERSONAL HEALTH CARD")
    pdf.setFillColor(colors.HexColor("#dcebe4"))
    pdf.roundRect(26, 119, 91, 112, 9, fill=1, stroke=0)
    path = Path(settings.PRIVATE_MEDIA_ROOT) / patient.photo_storage_name
    if patient.photo_storage_name and path.is_file():
        pdf.drawImage(
            ImageReader(str(path)),
            30,
            123,
            83,
            104,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    else:
        pdf.setFillColor(colors.HexColor("#6c8e81"))
        pdf.circle(71.5, 190, 17, fill=1, stroke=0)
        pdf.roundRect(44, 138, 55, 30, 13, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#163c32"))
    pdf.setFont("Helvetica-Bold", 16)
    name = patient.user.name
    while pdf.stringWidth(name, "Helvetica-Bold", 16) > 250:
        name = name[:-2]
    pdf.drawString(135, 213, name)
    pdf.setFillColor(colors.HexColor("#677d74"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(136, 190, "PATIENT ID")
    pdf.setFillColor(colors.HexColor("#12594b"))
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(135, 173, patient.user.account_id)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(136, 158, "Health record: " + patient.health_id)
    pdf.setFillColor(colors.HexColor("#677d74"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(136, 143, "DATE OF BIRTH")
    pdf.drawString(268, 143, "BLOOD GROUP")
    pdf.setFillColor(colors.HexColor("#163c32"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(135, 126, str(patient.date_of_birth or "Not recorded"))
    pdf.drawString(
        268, 126, patient.blood_group if patient.blood_group != "unknown" else "Unknown"
    )
    pdf.drawImage(
        ImageReader(BytesIO(qr_bytes(patient.card_locator))), 407, 130, 108, 108
    )
    pdf.setFillColor(colors.HexColor("#677d74"))
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(461, 120, "SCAN TO IDENTIFY")
    pdf.setStrokeColor(colors.HexColor("#dcebe4"))
    pdf.line(26, 98, 514, 98)
    pdf.setFillColor(colors.HexColor("#526b60"))
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        26, 73, "Keep this card with you when visiting your doctor or pharmacy."
    )
    pdf.setFont("Helvetica", 8)
    pdf.drawString(26, 48, "Private records require an approved provider to sign in.")
    pdf.drawString(
        26, 32, "Local application ID. This is not a government health card."
    )
    pdf.save()
    buffer.seek(0)
    return FileResponse(
        buffer,
        as_attachment=True,
        filename="medylink-card.pdf",
        content_type="application/pdf",
    )


def prescription_pdf(data):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, title="Prescription", leftMargin=36, rightMargin=36
    )
    styles = getSampleStyleSheet()

    def p(value, style="Normal"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    flow = [
        p("MedyLink · Prescription", "Title"),
        Spacer(1, 14),
        p(data["patient"]["name"], "Heading2"),
        p(data["patient"]["health_id"]),
        p(
            "Doctor: "
            + data["doctor_name"]
            + " · Registration: "
            + data["doctor_registration"]
        ),
        p("Prescription: " + data["id"]),
        p("Valid until: " + str(data["valid_until"])),
        p("Status: " + data["status"]),
        Spacer(1, 16),
    ]
    for item in data["items"]:
        flow += [
            p(item["medicine"], "Heading3"),
            p("Directions: " + item["dosage"]),
            p(item["instructions"]),
            p(
                "Prescribed: "
                + item["quantity"]
                + " "
                + item["unit"]
                + " · Remaining: "
                + item["remaining"]
                + " "
                + item["unit"]
            ),
            Spacer(1, 8),
        ]
    flow += [
        p("Prescription instructions", "Heading2"),
        p(data["notes"]),
        p("Allergies", "Heading2"),
        p("Status: " + data["allergy_status"]),
    ]
    for allergy in data["allergies"]:
        flow.append(
            p(
                allergy["name"]
                + " — "
                + allergy["notes"]
                + " ("
                + allergy["source"]
                + ")"
            )
        )
    flow += [
        Spacer(1, 16),
        p(
            "Clinical directions entered by the prescribing doctor. This application does not provide medicine advice."
        ),
    ]
    document.build(flow)
    buffer.seek(0)
    return FileResponse(
        buffer,
        as_attachment=True,
        filename="prescription.pdf",
        content_type="application/pdf",
    )


def photo_url(patient):
    if not patient.photo_storage_name:
        return None
    revision = hashlib.sha256(patient.photo_storage_name.encode()).hexdigest()[:12]
    return f"/api/v1/patients/{patient.id}/photo/?v={revision}"


def patient_identity(patient):
    return dict(
        id=str(patient.id),
        account_id=patient.user.account_id,
        name=patient.user.name,
        health_id=patient.health_id,
        date_of_birth=patient.date_of_birth,
        photo_url=photo_url(patient),
    )


def report(report):
    return dict(
        id=str(report.id),
        patient_id=str(report.patient_id),
        record_id=str(report.record_id) if report.record_id else None,
        name=report.name,
        title=report.title,
        content_type=report.content_type,
        size_bytes=report.size_bytes,
        uploaded_by=dict(
            id=str(report.uploaded_by_id),
            name=report.uploaded_by.name,
            role=report.uploaded_by.role,
        ),
        created_at=report.created_at,
        download_url=f"/api/v1/reports/{report.id}/download/",
        view_url=f"/api/v1/reports/{report.id}/view/",
        extraction=report.extraction or {"status": "unsupported"},
    )


def visit(consultation):
    applications = getattr(consultation.doctor, "visit_applications", None)
    app = (applications[0] if applications else None) if applications is not None else consultation.doctor.applications.order_by("-version").first()
    return dict(
        id=str(consultation.id),
        created_at=consultation.created_at,
        doctor=dict(
            id=str(consultation.doctor_id),
            account_id=consultation.doctor.account_id,
            name=consultation.doctor.name,
            qualification=app.qualification if app else "",
            specialty=app.specialty if app else "",
            clinic_name=app.clinic_name if app else "",
        ),
        record=record(consultation),
        prescriptions=[prescription(rx) for rx in consultation.prescription_set.all()],
        reports=[report(item) for item in consultation.reports.all()],
    )
