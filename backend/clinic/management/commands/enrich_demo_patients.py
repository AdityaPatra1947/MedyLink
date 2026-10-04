"""Add report-backed histories to exactly the first five mapped synthetic patients."""

import io
import json
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader

from accounts.models import User
from clinic.demo_report_fixture import durations, monthly_dates, pdf_digest, render_report, stable_id, visit_data
from clinic.models import AuditEvent, ClinicalEntry, DoctorPatient, MedicalRecord, MedicalReport, Patient, Prescription, PrescriptionItem, ProviderApplication
from clinic.report_extraction import extract_report_observations, parse_monthly_pdf
from clinic.services import approved
from clinic.uploads import private_file_batch, save_private_upload, validate_upload


class Command(BaseCommand):
    help = "Generate 60 fictional monthly reports for PAT0001..PAT0005. Database changes require --apply and dedicated synthetic settings."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--as-of", default=timezone.localdate().isoformat())
        parser.add_argument("--mapping", type=Path, default=settings.BASE_DIR.parent / ".local/synthetic/mumbai_stations_v1/import-map.json")
        parser.add_argument("--output", type=Path, default=settings.BASE_DIR.parent / "output/pdf/first-five-patients")

    def handle(self, *args, **options):
        if not getattr(settings, "SYNTHETIC_IMPORT_ALLOWED", False) or not getattr(settings, "SYNTHETIC_REPORT_EXTRACTION_ALLOWED", False):
            raise CommandError("This command requires the explicitly enabled synthetic environment.")
        if not settings.DATABASES["default"]["NAME"].startswith("synthetic_"):
            raise CommandError("The target must be a dedicated synthetic_ database.")
        try:
            as_of = date.fromisoformat(options["as_of"])
            if as_of > timezone.localdate() or as_of.year < 2020:
                raise ValueError
            mapping = json.loads(options["mapping"].read_text(encoding="utf-8"))
            if mapping["dataset_id"] != "mumbai_stations_v1" or mapping["synthetic"] is not True:
                raise ValueError
            entities = mapping["entities"]
        except (ValueError, KeyError, OSError):
            raise CommandError("A valid past as-of date and matching synthetic import mapping are required.") from None
        patients = []
        for index in range(5):
            sid = f"PAT{index + 1:04}"
            patient = Patient.objects.select_related("user").get(pk=entities["patients"][sid]["id"])
            if str(patient.user_id) != entities["users"][sid]["id"] or patient.user.role != "patient":
                raise CommandError(f"The expected existing test patient {sid} does not match; no data was written.")
            patients.append(patient)
        doctor_ids = [entry["id"] for sid, entry in sorted(entities["users"].items()) if sid.startswith("DOC")]
        doctors = list(User.objects.filter(pk__in=doctor_ids, role="doctor").order_by("name"))
        if len(doctors) < 3:
            raise CommandError("At least three existing synthetic doctors are required.")
        applications = {}
        for doctor in doctors:
            approved(doctor)
            application = ProviderApplication.objects.get(provider=doctor, is_current=True, status="approved")
            if not application.registration_number.startswith("SYNTHETIC-NOT-A-LICENSE-"):
                raise CommandError("Every selected doctor must be an existing synthetic provider.")
            applications[doctor.pk] = application

        output = options["output"].resolve()
        output.mkdir(parents=True, exist_ok=True)
        rows, manifest = [], {"version": "monthly-demo-v1", "synthetic": True, "as_of": as_of.isoformat(), "patients": []}
        for index, (patient, count) in enumerate(zip(patients, durations())):
            sid = f"PAT{index + 1:04}"
            folder = output / sid
            folder.mkdir(exist_ok=True)
            entry = {"source_id": sid, "patient_id": str(patient.pk), "name": patient.user.name, "email": patient.user.email,
                     "account_id": patient.user.account_id, "months": count, "reports": []}
            for month_index, day in enumerate(monthly_dates(as_of, count)):
                doctor = doctors[(index * 2 + month_index) % len(doctors)]
                application = applications[doctor.pk]
                visit = visit_data(index, sid, day, month_index, count)
                data = render_report(patient, doctor, application, visit)
                if len(PdfReader(io.BytesIO(data)).pages) != 2:
                    raise CommandError("A monthly report overflowed its two-page layout; no database changes were made.")
                extracted = parse_monthly_pdf(io.BytesIO(data), patient, doctor)
                expected = (visit["systolic"], visit["diastolic"], visit["glucose"])
                actual = (extracted.get("blood_pressure", {}).get("systolic"), extracted.get("blood_pressure", {}).get("diastolic"), extracted.get("blood_sugar", {}).get("value"))
                if actual != expected or extracted["adherence"]["daily"] != visit["daily"]:
                    raise CommandError("The printed PDF observations failed their round-trip extraction check.")
                name = f"{sid}-{day:%Y-%m}-bp-glucose.pdf"
                (folder / name).write_bytes(data)
                report_id = stable_id("report", sid, f"{day:%Y%m}")
                rows.append((patient, doctor, application, visit, name, data, report_id))
                entry["reports"].append({"id": str(report_id), "path": str(folder / name), "sha256": pdf_digest(data),
                                         "doctor": doctor.name, "doctor_id": doctor.account_id, "date": day.isoformat(),
                                         "blood_pressure": f"{visit['systolic']}/{visit['diastolic']}", "fasting_glucose": visit["glucose"],
                                         "scheduled_doses": extracted["adherence"]["scheduled_doses"], "taken_doses": extracted["adherence"]["taken_doses"]})
            manifest["patients"].append(entry)
            self.stdout.write(f"{sid}: {patient.user.name} - {count} monthly PDFs validated")
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if not options["apply"]:
            self.stdout.write(self.style.SUCCESS(f"Preview complete: {len(rows)} PDFs. No database changes. Use --apply to import."))
            return

        created = skipped = 0
        # File cleanup wraps the database transaction, including a failed commit.
        with private_file_batch() as paths:
            with transaction.atomic():
                list(User.objects.select_for_update().filter(pk__in=[doctor.pk for doctor in doctors]).order_by("pk"))
                list(Patient.objects.select_for_update().filter(pk__in=[patient.pk for patient in patients]).order_by("pk"))
                login_before = list(User.objects.filter(pk__in=[patient.user_id for patient in patients]).order_by("pk").values("id", "email", "password", "account_id"))
                conditions_checked = set()
                existing_reports = {row.pk: row for row in MedicalReport.objects.filter(pk__in=[row[-1] for row in rows])}
                for patient, doctor, application, visit, name, data, report_id in rows:
                    existing = existing_reports.get(report_id)
                    if existing:
                        # Rebranding new output never replaces an already-issued
                        # report with its original reference and private PDF bytes.
                        references = {visit["report_reference"], visit["report_reference"].replace("ML-DEMO-", "AT-DEMO-", 1)}
                        if existing.patient_id != patient.pk or existing.uploaded_by_id != doctor.pk or existing.extraction.get("report_reference") not in references:
                            raise CommandError("A prior demo report conflicts with this fixture; existing finalized data was not replaced.")
                        skipped += 1
                        continue
                    month = f"{visit['date']:%Y%m}"
                    record = MedicalRecord.objects.create(
                        id=stable_id("record", visit["source_id"], month), patient=patient, doctor=doctor,
                        complaint=visit["complaint"], diagnosis=visit["diagnosis"], notes=visit["notes"],
                        vitals={},
                    )
                    MedicalRecord.objects.filter(pk=record.pk).update(created_at=visit["measured_at"])
                    upload = SimpleUploadedFile(name, data, content_type="application/pdf")
                    checked = validate_upload(upload, kind="report")
                    report = MedicalReport.objects.create(
                        id=report_id, patient=patient, uploaded_by=doctor, record=record, name=name,
                        title=f"{visit['date']:%B %Y} - blood pressure and fasting glucose",
                        storage_name=save_private_upload(checked, paths), content_type=checked.content_type, size_bytes=len(data),
                    )
                    result = extract_report_observations(report, io.BytesIO(data))
                    if result.get("status") != "extracted":
                        raise CommandError("The PDF could not be extracted; the import was rolled back.")
                    prescription = Prescription.objects.create(
                        id=stable_id("prescription", visit["source_id"], month), patient=patient, doctor=doctor,
                        application=application, record=record, valid_until=visit["measured_at"] + timedelta(days=30),
                        notes="Synthetic maintenance prescription. Continue the established fictional regimen; review diary, tolerance and BP/glucose at the next monthly visit.",
                    )
                    Prescription.objects.filter(pk=prescription.pk).update(created_at=visit["measured_at"])
                    PrescriptionItem.objects.bulk_create([
                        PrescriptionItem(id=stable_id("medicine", visit["source_id"], month + str(n)), prescription=prescription,
                                         **{key: value for key, value in item.items() if key != "daily_doses"})
                        for n, item in enumerate(visit["medicines"])
                    ])
                    DoctorPatient.objects.get_or_create(doctor=doctor, patient=patient)
                    if patient.pk not in conditions_checked:
                        known = {name.casefold() for name in ClinicalEntry.objects.filter(patient=patient, kind="condition", resolved_at__isnull=True).values_list("name", flat=True)}
                        for n, condition in enumerate(visit["diagnosis"].split("; ")):
                            aliases = {condition.casefold()}
                            if condition == "Essential hypertension":
                                aliases.add("hypertension")
                            if known.intersection(aliases):
                                continue
                            entry, is_new = ClinicalEntry.objects.get_or_create(id=stable_id("condition", visit["source_id"], str(n)), defaults={
                                "patient": patient, "author": doctor, "kind": "condition", "name": condition,
                                "notes": "Fictional established history documented during monthly follow-up; not an automated diagnosis from a report.", "source": "clinician_recorded",
                            })
                            if is_new:
                                ClinicalEntry.objects.filter(pk=entry.pk).update(created_at=visit["measured_at"])
                        conditions_checked.add(patient.pk)
                    AuditEvent.objects.create(actor=doctor, patient=patient, event="report.synthetic_import", resource_id=str(report.pk))
                    created += 1
                    if created % 10 == 0:
                        self.stdout.write(f"Prepared {created}/{len(rows)} monthly reports in the import transaction...")
                login_after = list(User.objects.filter(pk__in=[patient.user_id for patient in patients]).order_by("pk").values("id", "email", "password", "account_id"))
                if login_before != login_after:
                    raise CommandError("The existing login identities changed unexpectedly; import rolled back.")
        self.stdout.write(self.style.SUCCESS(f"Imported {created} monthly reports; {skipped} already imported. Five patient identities and passwords preserved."))
