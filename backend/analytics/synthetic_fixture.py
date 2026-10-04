"""Portable expansion fixtures built only from the public generator and stations.

Everything above apply_fixture is standard-library-only and database-independent.
Reproduction validation checks every field, relationship and deterministic ID, not
just a checksum that could be rewritten alongside a tampered input.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .synthetic_generation import BATCH_KEY, END, START, VERSION, generate_patients

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIRECTORY = ROOT / "data/synthetic/mumbai_disease_v1"
BASE_DIRECTORY = ROOT / "data/synthetic/mumbai_stations_v1"
FIXTURE_ID = "mumbai_disease_v1"
MAX_FILE_BYTES = 40 * 1024 * 1024


class FixtureError(ValueError):
    pass


def _json(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _parse(raw):
    def unique_object(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (TypeError, ValueError, UnicodeError):
        raise FixtureError("Fixture contains invalid JSON or duplicate fields.") from None


def _read(path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise FixtureError("Fixture file exceeds the 40 MiB limit.")
        return path.read_bytes()
    except OSError:
        raise FixtureError("A required fixture file could not be read.") from None


def _digest(raw):
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _base_source():
    raw = _read(BASE_DIRECTORY / "dataset.json")
    base = _parse(raw)
    manifest = _parse(_read(BASE_DIRECTORY / "manifest.json"))
    if (not isinstance(base, dict) or not isinstance(manifest, dict)
            or base.get("metadata", {}).get("dataset_id") != BATCH_KEY
            or base.get("metadata", {}).get("synthetic") is not True
            or manifest.get("files", {}).get("dataset.json") != _digest(raw)
            or len(base.get("patients", [])) != 1000
            or len(base.get("stations", [])) != 34):
        raise FixtureError("The unchanged, hash-verified 1,000-patient base fixture is required.")
    stations = [{"key": row["station_id"], "name": row["station_name"],
                 "latitude": row["latitude"], "longitude": row["longitude"]}
                for row in base["stations"]]
    base_ids = {row["source_id"]: str(uuid5(NAMESPACE_URL, f"arogyatrack:{BATCH_KEY}:patients:{row['source_id']}"))
                for row in base["patients"]}
    return stations, base_ids, _digest(raw)


def _package(count=3000, seed=42):
    if type(count) is not int or not 1 <= count <= 4000 or type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise FixtureError("Expansion requires 1..4,000 patients and a non-negative 64-bit seed.")
    stations, base_ids, base_hash = _base_source()
    generated = generate_patients(count, seed, stations)
    patients = [{key: value for key, value in row.items() if key != "visits"} for row in generated]
    visits = [{"patient_id": row["id"], **visit} for row in generated for visit in row["visits"]]
    payloads = {"patients.jsonl": ("\n".join(_json(row) for row in patients) + "\n").encode("utf-8"),
                "visits.jsonl": ("\n".join(_json(row) for row in visits) + "\n").encode("utf-8")}
    counts = {"patients": count, "visits": len(visits), "stations": len(stations),
              "derived_labs": sum(visit["vitals"][key] is not None for visit in visits
                                  for key in ("glucose_mg_dl", "hemoglobin", "platelets")),
              "derived_disease_observations": sum(1 + len(visit["secondary_disease_codes"]) for visit in visits),
              "base_patients": len(base_ids), "combined_patients": len(base_ids) + count}
    manifest = {"schema_version": 1, "fixture_id": FIXTURE_ID, "synthetic": True,
                "generator_version": VERSION, "seed": seed,
                "history_start": START.isoformat(), "history_end": END.isoformat(),
                "account_policy": {"is_active": False, "password": "unusable", "login_credentials_included": False},
                "base": {"dataset_id": BATCH_KEY, "path": "data/synthetic/mumbai_stations_v1/dataset.json", **base_hash},
                "source": "Offline deterministic generator; public base-fixture station anchors. No database export.",
                "station_provenance": "data/reference/STATION_SOURCES.md",
                "counts": counts,
                "primary_disease_patients": dict(sorted(Counter(row["visits"][0]["primary_disease_code"] for row in generated).items())),
                "files": {name: _digest(raw) for name, raw in payloads.items()}}
    return {"manifest": manifest, "patients": generated, "stations": stations,
            "base_patient_ids": base_ids, "payloads": payloads}


def build_fixture(directory=DEFAULT_DIRECTORY, *, count=3000, seed=42):
    """Deterministic local generation; no Django initialization or secret inputs."""
    package = _package(count, seed)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, raw in package["payloads"].items():
        (directory / name).write_bytes(raw)
    (directory / "manifest.json").write_text(json.dumps(package["manifest"], indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return package["manifest"]


def load_fixture(directory=DEFAULT_DIRECTORY):
    """Validate the entire downloaded fixture before opening a DB connection."""
    directory = Path(directory)
    manifest = _parse(_read(directory / "manifest.json"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("counts"), dict):
        raise FixtureError("A versioned synthetic expansion manifest is required.")
    package = _package(manifest["counts"].get("patients"), manifest.get("seed"))
    if _json(manifest) != _json(package["manifest"]):
        raise FixtureError("Manifest identity, schema, counts, dates, provenance or hashes do not match the reproducible fixture.")
    for name, expected in package["payloads"].items():
        raw = _read(directory / name)
        if _digest(raw) != manifest["files"][name]:
            raise FixtureError("Expansion file checksum or byte count does not match its manifest.")
        # Canonical, deterministic bytes validate all rows, including keys, schema,
        # UUIDs, cross-row relationships, dates, finite measurements and labels.
        if raw != expected:
            raise FixtureError("Expansion rows differ from the deterministic public generator.")
    package["manifest_hash"] = hashlib.sha256(_read(directory / "manifest.json")).hexdigest()
    return package


def validate_target(package, batch, stations):
    """Called under the append transaction's batch lock, before any insert."""
    from django.core.management.base import CommandError

    manifest = package["manifest"]
    if batch.dataset_hash != manifest["base"]["sha256"] or batch.patient_count != manifest["counts"]["base_patients"]:
        raise CommandError("Import this expansion's base clinical fixture and analytics sidecars first.")
    base_ids = package["base_patient_ids"]
    existing_base = {key: str(patient) for key, patient in batch.areas.filter(source_key__in=base_ids).values_list("source_key", "patient_id")}
    if existing_base != base_ids:
        raise CommandError("The complete, matching base patient cohort must already be imported.")
    actual = [{"key": row.key, "name": row.name, "latitude": row.latitude, "longitude": row.longitude} for row in stations]
    if sorted(actual, key=lambda row: row["key"]) != sorted(package["stations"], key=lambda row: row["key"]):
        raise CommandError("Database stations differ from the expansion's public station references.")


def validate_existing(package, batch, existing_areas):
    """A repeat is a no-op only for intact matching entities, never a silent skip."""
    from accounts.models import User
    from clinic.models import LabResult, MedicalRecord, Patient
    from django.core.management.base import CommandError

    from .synthetic_generation import NAMESPACE

    rows = [row for row in package["patients"] if row["source_key"] in existing_areas]
    expected_records, expected_labs, expected_observations, users = {}, {}, {}, set()
    for row in rows:
        if str(existing_areas[row["source_key"]]) != row["id"]:
            raise CommandError("Existing expansion source keys conflict with the fixture; no records were changed.")
        users.add(row["user_id"])
        for visit in row["visits"]:
            expected_records[visit["id"]] = row["id"]
            for key in ("glucose_mg_dl", "hemoglobin", "platelets"):
                if visit["vitals"][key] is not None:
                    expected_labs[str(uuid5(NAMESPACE, visit["id"] + ":" + key))] = row["id"]
            for code in (visit["primary_disease_code"], *visit["secondary_disease_codes"]):
                expected_observations[f"{VERSION}:{visit['id']}:{code}"] = row["id"]
    actual_records = {str(pk): str(patient) for pk, patient in MedicalRecord.objects.filter(pk__in=expected_records).values_list("id", "patient_id")}
    actual_labs = {str(pk): str(patient) for pk, patient in LabResult.objects.filter(pk__in=expected_labs).values_list("id", "patient_id")}
    actual_observations = {key: str(patient) for key, patient in batch.observations.filter(import_key__in=expected_observations).values_list("import_key", "patient_id")}
    expected_patients = {row["id"]: row["user_id"] for row in rows}
    actual_patients = {str(pk): str(user) for pk, user in Patient.objects.filter(pk__in=expected_patients).values_list("id", "user_id")}
    accounts = list(User.objects.filter(pk__in=users).only("id", "is_active", "password", "role"))
    if (actual_patients != expected_patients or actual_records != expected_records or actual_labs != expected_labs or actual_observations != expected_observations
            or len(accounts) != len(users) or any(user.is_active or user.has_usable_password() or user.role != "patient" for user in accounts)):
        raise CommandError("An existing expansion is incomplete or has conflicting account policy; no records were changed.")


def apply_fixture(package):
    from django.core.management.base import CommandError
    from django.db import IntegrityError

    from .synthetic_generation import append_synthetic_patients

    try:
        return append_synthetic_patients(count=package["manifest"]["counts"]["patients"],
                                        seed=package["manifest"]["seed"], fixture=package)
    except IntegrityError:
        raise CommandError("Expansion identities conflict with database constraints; the append transaction was rolled back.") from None
