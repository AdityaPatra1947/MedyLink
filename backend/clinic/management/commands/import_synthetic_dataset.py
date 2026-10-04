"""Validate offline, or explicitly import into an empty dedicated synthetic DB."""

import hashlib
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import password_changed, validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import connection, transaction
from django.utils import timezone

from accounts.identifiers import generate_account_id
from accounts.models import SecurityEvent, User
from clinic.models import (
    ClinicalEntry, DoctorPatient, LabResult, MedicalRecord,
    MedicationAdherenceLog, Patient, Prescription, PrescriptionItem,
    ProviderApplication,
)

DATASET_ID = "mumbai_stations_v1"
DOMAIN = "@synthetic.medylink.test"
# Original exports retain their addresses and deterministic identities.
SYNTHETIC_DOMAINS = (DOMAIN, "@synthetic.arogyatrack.test")
PROFILE_FIELDS = {
    "phone": 30, "address": 500, "emergency_contact": 250,
    "gender": 20, "blood_group": 8, "allergy_status": 15,
}
APPLICATION_FIELDS = {
    "registration_number": 100, "registering_body": 150,
    "specialty": 150, "qualification": 150, "practice_address": 500,
    "shop_name": 180, "shop_license": 100, "reason": 1000,
    "evidence_reviewed": 1000,
}


def fail(path, message):
    # Paths describe schema locations, never submitted values or credentials.
    raise CommandError(f"{path}: {message}")


def text_value(obj, key, limit, path, required=False):
    value = obj.get(key, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        fail(f"{path}.{key}", f"expected {'nonempty ' if required else ''}text up to {limit} characters")
    return value


def object_value(value, path):
    if not isinstance(value, dict):
        fail(path, "expected an object")
    return value


def list_value(value, path, maximum=1000, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        fail(path, f"expected an array with {minimum}..{maximum} items")
    return value


def date_value(value, path):
    try:
        if not isinstance(value, str):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        fail(path, "expected an ISO date")


def stamp(value, path):
    try:
        if not isinstance(value, str):
            raise ValueError
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(result):
            raise ValueError
        return result
    except ValueError:
        fail(path, "expected an ISO datetime with timezone")


def decimal_value(value, path, digits, places, positive=False):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or (positive and result <= 0):
            raise ValueError
        from django.core.validators import DecimalValidator
        DecimalValidator(digits, places)(result)
        return result
    except (InvalidOperation, ValueError, ValidationError):
        fail(path, "invalid decimal precision or range")


def load_json(path):
    try:
        if path.stat().st_size > 100 * 1024 * 1024:
            raise CommandError("Input file exceeds the 100 MiB limit.")
        raw = path.read_bytes()
        data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        return object_value(data, "root"), hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, UnicodeError):
        raise CommandError("Unable to read a valid UTF-8 JSON input file.") from None


def validate_dataset(data, credentials):
    """Pure validation: no ORM queries, sessions, email, or database connection."""
    meta = object_value(data.get("metadata"), "metadata")
    if meta.get("schema_version") != 1 or meta.get("synthetic") is not True:
        fail("metadata", "requires schema_version=1 and synthetic=true")
    dataset_id = meta.get("dataset_id")
    if not isinstance(dataset_id, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,80}", dataset_id):
        fail("metadata.dataset_id", "requires 1..80 letters, digits, or underscores")
    as_of = date_value(meta.get("as_of"), "metadata.as_of")
    cutoff = datetime.combine(as_of, time.max, tzinfo=dt_timezone.utc)
    if credentials.get("dataset_id") != dataset_id or credentials.get("synthetic") is not True:
        fail("credentials", "dataset identity or synthetic marker does not match")
    list_value(data.get("stations"), "stations", maximum=1000)
    providers = list_value(data.get("providers"), "providers", maximum=100, minimum=1)
    patients = list_value(data.get("patients"), "patients", maximum=5000, minimum=1)
    seen_sources, seen_emails, identities, doctors = set(), set(), {}, {}

    def source(obj, path, fallback=None):
        value = obj.get("source_id", fallback)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
            fail(path + ".source_id", "invalid source identifier")
        if value in seen_sources:
            fail(path + ".source_id", "duplicate source identifier")
        seen_sources.add(value)
        obj["source_id"] = value
        return value

    def historical(obj, key, path):
        value = stamp(obj.get(key), path + "." + key)
        if value > cutoff:
            fail(path + "." + key, "must not be later than metadata.as_of")
        obj[key] = value
        return value

    def identity(row, path, role):
        sid = source(row, path)
        user = object_value(row.get("user"), path + ".user")
        email = text_value(user, "email", 254, path, True)
        try:
            validate_email(email)
        except ValidationError:
            fail(path + ".user.email", "invalid email format")
        if not email.endswith(SYNTHETIC_DOMAINS) or email != email.strip().lower() or email in seen_emails:
            fail(path + ".user.email", "requires a unique normalized synthetic email")
        seen_emails.add(email)
        text_value(user, "name", 150, path, True)
        text_value(user, "phone", 30, path)
        if user.get("role", role) != role:
            fail(path + ".user.role", "role mismatch")
        user["role"] = role
        historical(user, "created_at", path + ".user")
        identities[sid] = user
        return sid, user

    credential_keys, shop_keys = set(), set()
    for i, row in enumerate(providers):
        path = f"providers[{i}]"
        object_value(row, path)
        role = object_value(row.get("user"), path + ".user").get("role")
        if role not in {"doctor", "pharmacist", "admin"}:
            fail(path, "unsupported provider role")
        sid, user = identity(row, path, role)
        if role == "admin":
            if "application" in row:
                fail(path, "administrator must not have a provider application")
            continue
        app = object_value(row.get("application"), path + ".application")
        for key, limit in APPLICATION_FIELDS.items():
            text_value(app, key, limit, path + ".application", key in {
                "registration_number", "registering_body", "practice_address", "reason", "evidence_reviewed",
            })
        for key in (("specialty", "qualification") if role == "doctor" else ("shop_name", "shop_license")):
            text_value(app, key, APPLICATION_FIELDS[key], path + ".application", True)
        key = (app["registering_body"], app["registration_number"])
        if key in credential_keys:
            fail(path, "duplicate provider credential")
        credential_keys.add(key)
        if app.get("shop_license"):
            key = (app["registering_body"], app["shop_license"])
            if key in shop_keys:
                fail(path, "duplicate shop license")
            shop_keys.add(key)
        if app.get("shop_license_expires"):
            app["shop_license_expires"] = date_value(app["shop_license_expires"], path + ".shop_license_expires")
        if role == "pharmacist" and (not app.get("shop_license_expires") or app["shop_license_expires"] < as_of):
            fail(path, "pharmacy license must be valid as of the dataset date")
        app["valid_until"] = stamp(app.get("valid_until"), path + ".valid_until")
        if app["valid_until"] <= cutoff:
            fail(path, "provider approval must extend beyond the dataset date")
        if role == "doctor":
            doctors[sid] = user
    if not doctors:
        fail("providers", "at least one doctor is required")

    def doctor(row, path):
        if row.get("doctor_source_id") not in doctors:
            fail(path + ".doctor_source_id", "must reference a dataset doctor")

    for i, row in enumerate(patients):
        path = f"patients[{i}]"
        object_value(row, path)
        patient_sid, user = identity(row, path, "patient")
        profile = object_value(row.get("profile"), path + ".profile")
        for key, limit in PROFILE_FIELDS.items():
            text_value(profile, key, limit, path + ".profile")
        dob = date_value(profile.get("date_of_birth"), path + ".profile.date_of_birth")
        age = as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))
        if dob < date(1900, 1, 1) or age < 18:
            fail(path + ".profile.date_of_birth", "requires an adult born on or after 1900-01-01")
        profile["date_of_birth"] = dob
        for key, choices in {
            "gender": {"", "female", "male", "other", "prefer_not_to_say"},
            "blood_group": {"unknown", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"},
            "allergy_status": {"unknown", "none_known", "reported"},
        }.items():
            if profile.get(key, "" if key == "gender" else "unknown") not in choices:
                fail(path + ".profile." + key, "invalid choice")
        records = {}
        for kind in ("records", "entries", "labs", "prescriptions", "adherence"):
            for j, child in enumerate(list_value(row.get(kind, []), path + "." + kind)):
                child_path = f"{path}.{kind}[{j}]"
                object_value(child, child_path)
                source(child, child_path, f"{patient_sid}-{kind}-{j + 1}")
                if kind in {"records", "labs", "prescriptions"}:
                    doctor(child, child_path)
                if kind == "records":
                    historical(child, "recorded_at", child_path)
                    for field, length in {"complaint": 1000, "diagnosis": 1000, "notes": 10000}.items():
                        text_value(child, field, length, child_path, field == "complaint")
                    vitals = object_value(child.get("vitals", {}), child_path + ".vitals")
                    if len(vitals) > 20 or any(
                        not isinstance(k, str) or len(k) > 60
                        or type(v) not in {str, int, float} or len(str(v)) > 100
                        or (isinstance(v, float) and not math.isfinite(v))
                        for k, v in vitals.items()
                    ):
                        fail(child_path + ".vitals", "invalid measurement names or values")
                    records[child["source_id"]] = child
                elif kind == "entries":
                    if child.get("kind") not in {"condition", "allergy"} or child.get("source") not in {"patient_reported", "clinician_recorded"}:
                        fail(child_path, "invalid clinical entry kind or source")
                    author = child.get("author_source_id")
                    if author != patient_sid and author not in doctors:
                        fail(child_path, "entry author must be this patient or a dataset doctor")
                    if (child["source"] == "patient_reported") != (author == patient_sid):
                        fail(child_path, "entry source must match the author role")
                    text_value(child, "name", 200, child_path, True)
                    text_value(child, "notes", 1000, child_path)
                    historical(child, "recorded_at", child_path)
                elif kind == "labs":
                    text_value(child, "name", 120, child_path, True)
                    text_value(child, "unit", 40, child_path, True)
                    child["value"] = decimal_value(child.get("value"), child_path + ".value", 16, 5)
                    historical(child, "measured_at", child_path)
                elif kind == "prescriptions":
                    issued = historical(child, "issued_at", child_path)
                    child["valid_until"] = stamp(child.get("valid_until"), child_path + ".valid_until")
                    if child["valid_until"] <= issued:
                        fail(child_path, "prescription expiry must follow issuance")
                    record = records.get(child.get("record_source_id"))
                    if not record or record["doctor_source_id"] != child["doctor_source_id"]:
                        fail(child_path, "prescription record must belong to this patient and doctor")
                    if issued < record["recorded_at"]:
                        fail(child_path, "prescription must not predate its visit")
                    text_value(child, "notes", 2000, child_path)
                    for item in list_value(child.get("items"), child_path + ".items", maximum=30, minimum=1):
                        object_value(item, child_path + ".items")
                        for key, length in {"medicine": 200, "dosage": 250, "instructions": 1000, "unit": 40}.items():
                            text_value(item, key, length, child_path + ".items", key != "instructions")
                        item["unit"] = item["unit"].strip().lower()
                        item["quantity"] = decimal_value(item.get("quantity"), child_path + ".quantity", 10, 3, positive=True)
                else:
                    child["date"] = date_value(child.get("date"), child_path + ".date")
                    scheduled, taken = child.get("scheduled_doses"), child.get("taken_doses")
                    if type(scheduled) is not int or type(taken) is not int or not 0 <= taken <= scheduled <= 10000 or scheduled < 1 or child["date"] > as_of:
                        fail(child_path, "invalid adherence date or dose counts")
        adherence_dates = [child["date"] for child in row.get("adherence", [])]
        if len(adherence_dates) != len(set(adherence_dates)):
            fail(path + ".adherence", "duplicate patient/date")

    passwords = {}
    for i, item in enumerate(list_value(credentials.get("accounts"), "credentials.accounts", maximum=5100)):
        path = f"credentials.accounts[{i}]"
        object_value(item, path)
        sid = item.get("source_id")
        user = identities.get(sid)
        if not user or sid in passwords or any(item.get(key) != user[key] for key in ("email", "name", "role")):
            fail(path, "credentials do not match exactly one dataset identity")
        password = text_value(item, "password", 1024, path, True)
        try:
            validate_password(password, User(email=user["email"], name=user["name"]))
        except ValidationError:
            fail(path + ".password", "password does not meet configured strength requirements")
        passwords[sid] = password
    if passwords.keys() != identities.keys():
        fail("credentials.accounts", "requires exactly one credential per dataset account")
    if len(set(passwords.values())) != len(passwords):
        fail("credentials.accounts", "each synthetic account requires a distinct password")
    return passwords


class Command(BaseCommand):
    help = "Validate synthetic JSON offline; --apply requires an empty dedicated synthetic PostgreSQL database."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        root = settings.BASE_DIR.parent
        parser.add_argument("--dataset", default=str(root / "data/synthetic" / DATASET_ID / "dataset.json"))
        parser.add_argument("--credentials", default=str(root / ".local/synthetic" / DATASET_ID / "credentials.json"))
        parser.add_argument("--mapping", default=str(root / ".local/synthetic" / DATASET_ID / "import-map.json"))
        parser.add_argument("--apply", action="store_true", help="Write after validation; default is a database-free dry run.")

    def require_target(self):
        db = settings.DATABASES["default"]
        if not settings.DEBUG or not getattr(settings, "SYNTHETIC_IMPORT_ALLOWED", False):
            raise CommandError("Apply requires DEBUG and config.synthetic_settings; normal settings are refused.")
        name = db.get("NAME", "")
        if (db.get("ENGINE") != "django.db.backends.postgresql"
            or not isinstance(name, str)
            or not re.fullmatch(r"synthetic_[A-Za-z0-9_]+", name)
            or name != getattr(settings, "SYNTHETIC_IMPORT_DATABASE_NAME", None)):
            raise CommandError("Apply requires the explicitly configured dedicated synthetic_ PostgreSQL database.")

    def handle(self, *args, **options):
        dataset_path = Path(options["dataset"]).expanduser().resolve()
        credentials_path = Path(options["credentials"]).expanduser().resolve()
        mapping_path = Path(options["mapping"]).expanduser().resolve()
        local = (settings.BASE_DIR.parent / ".local").resolve()
        if not credentials_path.is_relative_to(local) or not mapping_path.is_relative_to(local) or mapping_path in {local, credentials_path, dataset_path}:
            raise CommandError("Credentials and a separate mapping must be inside the repository's ignored .local directory.")
        data, checksum = load_json(dataset_path)
        credentials, _ = load_json(credentials_path)
        passwords = validate_dataset(data, credentials)
        count = len(data["patients"])
        if not options["apply"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run passed: {count} synthetic patients, {len(data['providers'])} providers. No database access or writes."))
            return
        self.require_target()
        mapping_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(mapping_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError:
            raise CommandError("Cannot exclusively create mapping file; an existing mapping is never overwritten.") from None
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as destination:
                # Reject an obviously populated target before expensive CPU work.
                # The authoritative emptiness check remains under the lock below.
                if User.objects.exists():
                    raise CommandError("Target user table is not empty. Repeat imports and overwrites are refused.")
                if not connection.in_atomic_block:
                    connection.close()
                prepared_hashes = self.prepare_password_hashes(passwords)
                # Hashing can take minutes; never reuse a connection left idle or
                # hold a database transaction/lock while preparing those hashes.
                if not connection.in_atomic_block:
                    connection.close()
                with transaction.atomic():
                    if connection.vendor == "postgresql":
                        # Block racing signups/imports while proving and populating emptiness.
                        with connection.cursor() as cursor:
                            cursor.execute("LOCK TABLE accounts_user IN SHARE ROW EXCLUSIVE MODE")
                    if User.objects.exists():
                        raise CommandError("Target user table is not empty. Repeat imports and overwrites are refused.")
                    mapping = self.import_rows(data, passwords, checksum, prepared_hashes=prepared_hashes)
                    json.dump(mapping, destination, indent=2)
                    destination.write("\n")
                    destination.flush()
                    os.fsync(destination.fileno())
        except Exception:
            mapping_path.unlink(missing_ok=True)
            raise
        self.stdout.write(self.style.SUCCESS(f"Imported {count} synthetic patients. Mapping: {mapping_path}"))

    def prepare_password_hashes(self, passwords):
        def encode(item):
            sid, password = item
            return sid, make_password(password)

        prepared = {}
        # PBKDF2 releases the GIL. Bound concurrency and retain Django's configured
        # work factor and fresh random salt for every individual credential.
        with ThreadPoolExecutor(max_workers=min(4, len(passwords))) as executor:
            for index, (sid, encoded) in enumerate(executor.map(encode, passwords.items()), start=1):
                prepared[sid] = encoded
                if index % 100 == 0 or index == len(passwords):
                    self.stdout.write(f"Prepared password hashes: {index}/{len(passwords)} synthetic accounts.")
                    self.stdout.flush()
        return prepared

    def import_rows(self, data, passwords, checksum, prepared_hashes=None):
        if prepared_hashes is None:
            prepared_hashes = self.prepare_password_hashes(passwords)
        dataset_id = data["metadata"]["dataset_id"]
        mapping = {"dataset_id": dataset_id, "synthetic": True, "dataset_sha256": checksum, "entities": {}}
        mapped, users, applications, pending = mapping["entities"], {}, {}, {}

        def uid(kind, sid):
            # A namespace is an identity contract, not display branding. Changing
            # it would make the same historical import create different UUIDs.
            return uuid5(NAMESPACE_URL, f"arogyatrack:{dataset_id}:{kind}:{sid}")

        def remember(kind, sid, obj, **extra):
            mapped.setdefault(kind, {})[sid] = {"id": str(obj.pk), **extra}

        def create(model, entity, sid, when, **fields):
            obj = model(id=uid(entity, sid), **fields)
            pending.setdefault(model, []).append((obj, when))
            remember(entity, sid, obj)
            return obj

        identities = [*data["providers"], *data["patients"]]
        account_ids, import_events = set(), []
        for row in identities:
            sid, source = row["source_id"], row["user"]
            # The locked, empty target permits batching without per-user savepoints.
            # Keep create_user's normalization, hasher, and role-ID invariants.
            user = User(
                email=source["email"].strip().lower(), id=uid("users", sid),
                name=source["name"], role=source["role"], phone=source.get("phone", ""),
                created_at=source["created_at"], email_verified_at=source["created_at"],
                storage_consent_at=source["created_at"], privacy_version="1.0",
            )
            user.password = prepared_hashes[sid]
            user._password = passwords[sid]
            for attempt in range(10):
                user.account_id = generate_account_id(user.role)
                if user.account_id not in account_ids:
                    account_ids.add(user.account_id)
                    break
            else:
                raise CommandError("Unable to generate a unique synthetic account ID.")
            users[sid] = user
            remember("users", sid, user, account_id=user.account_id)
            import_events.append(SecurityEvent(user=user, event="synthetic_dataset_import", metadata={
                "synthetic": True, "dataset_id": dataset_id, "source_id": sid, "dataset_sha256": checksum,
                "email_preverified_for_synthetic_test": True,
            }))
        User.objects.bulk_create(list(users.values()), batch_size=500)
        # AbstractBaseUser.save normally dispatches this after saving a new hash.
        for user in users.values():
            password_changed(user._password, user)
            user._password = None
        SecurityEvent.objects.bulk_create(import_events, batch_size=500)
        for row in data["providers"]:
            sid = row["source_id"]
            if "application" not in row:
                continue
            app = row["application"]
            fields = {key: app[key] for key in APPLICATION_FIELDS if key in app}
            fields.update({key: app[key] for key in ("valid_until", "shop_license_expires") if key in app})
            applications[sid] = create(ProviderApplication, "applications", sid, users[sid].created_at,
                provider=users[sid], version=1, is_current=True, status="approved", **fields)
        for row in data["patients"]:
            sid, profile = row["source_id"], row["profile"]
            fields = {key: profile[key] for key in (*PROFILE_FIELDS, "date_of_birth") if key in profile}
            patient = create(Patient, "patients", sid, users[sid].created_at, user=users[sid], **fields)
            mapped["patients"][sid]["health_id"] = patient.health_id
            records, saved_doctors = {}, set()
            for visit in row.get("records", []):
                doc = visit["doctor_source_id"]
                records[visit["source_id"]] = create(MedicalRecord, "records", visit["source_id"], visit["recorded_at"],
                    patient=patient, doctor=users[doc], complaint=visit["complaint"],
                    diagnosis=visit.get("diagnosis", ""), notes=visit.get("notes", ""), vitals=visit.get("vitals", {}))
                if doc not in saved_doctors:
                    create(DoctorPatient, "saved_patients", f"{doc}-{sid}", visit["recorded_at"], doctor=users[doc], patient=patient)
                    saved_doctors.add(doc)
            for entry in row.get("entries", []):
                create(ClinicalEntry, "entries", entry["source_id"], entry["recorded_at"],
                    patient=patient, author=users[entry["author_source_id"]],
                    kind=entry["kind"], name=entry["name"], notes=entry.get("notes", ""), source=entry["source"])
            for lab in row.get("labs", []):
                create(LabResult, "labs", lab["source_id"], lab["measured_at"], patient=patient,
                    recorded_by=users[lab["doctor_source_id"]], name=lab["name"], value=lab["value"],
                    unit=lab["unit"], measured_at=lab["measured_at"])
            for rx in row.get("prescriptions", []):
                doc = rx["doctor_source_id"]
                prescription = create(Prescription, "prescriptions", rx["source_id"], rx["issued_at"],
                    patient=patient, doctor=users[doc], application=applications[doc],
                    record=records[rx["record_source_id"]], valid_until=rx["valid_until"], notes=rx.get("notes", ""))
                for i, item in enumerate(rx["items"]):
                    create(PrescriptionItem, "prescription_items", f"{rx['source_id']}-{i + 1}", rx["issued_at"],
                        prescription=prescription, **{key: item.get(key, "") for key in ("medicine", "dosage", "instructions", "quantity", "unit")})
            for log in row.get("adherence", []):
                create(MedicationAdherenceLog, "adherence", log["source_id"],
                    datetime.combine(log["date"], time(12), tzinfo=dt_timezone.utc), patient=patient,
                    date=log["date"], scheduled_doses=log["scheduled_doses"], taken_doses=log["taken_doses"])
        # Parent-first order; UUID primary keys allow references before insertion.
        for model in (ProviderApplication, Patient, MedicalRecord, DoctorPatient,
                      ClinicalEntry, LabResult, Prescription, PrescriptionItem,
                      MedicationAdherenceLog):
            rows = pending.get(model, [])
            objects = [obj for obj, _ in rows]
            if not objects:
                continue
            model.objects.bulk_create(objects, batch_size=500)
            # auto_now_add overrides even bulk_create input; restore historical dates.
            for obj, when in rows:
                obj.created_at = when
            model.objects.bulk_update(objects, ["created_at"], batch_size=500)
        return mapping
