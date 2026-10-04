"""Hash-verified synthetic sidecars with explicit clinical lineage, no record edits."""

import hashlib
import json
import math
import re
from datetime import date, datetime
from datetime import timezone as dt_timezone
from pathlib import Path
from uuid import UUID

from accounts.models import SecurityEvent
from clinic.models import ClinicalEntry, MedicalRecord, Patient
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone

from .models import (
    DatasetBatch,
    DiseaseCode,
    DiseaseObservation,
    EvaluationTruth,
    PatientAreaObservation,
    StationArea,
)

DISEASE_LABELS = {
    "DENGUE": "Dengue",
    "INFLUENZA": "Influenza",
    "ASTHMA": "Asthma",
    "GASTROENTERITIS": "Gastroenteritis",
    "HYPERTENSION": "Hypertension",
    "TYPE2_DIABETES": "Type 2 diabetes",
    "ANEMIA": "Anemia",
    "HYPOTHYROIDISM": "Hypothyroidism",
    "MALARIA": "Malaria",
    "OSTEOARTHRITIS": "Osteoarthritis",
    "NO_RECORDED_DISEASE": "No disease recorded",
}
OBSERVATION_FIELDS = {
    "dataset_id",
    "is_synthetic",
    "patient_key",
    "record_key",
    "episode_key",
    "disease_code",
    "observed_at",
    "age_at_observation",
    "age_band",
    "station_id",
    "line_memberships",
    "synthetic_latitude",
    "synthetic_longitude",
    "coordinate_kind",
}


def error(message):
    raise CommandError(message)


def read_file(path):
    try:
        if path.stat().st_size > 100 * 1024 * 1024:
            error("Synthetic input file exceeds the 100 MiB limit.")
        content = path.read_bytes()
        return content, hashlib.sha256(content).hexdigest()
    except OSError:
        error("A required synthetic input file could not be read.")


def read_json(content):
    try:
        return json.loads(
            content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
        )
    except (ValueError, UnicodeError):
        error("Synthetic input contains invalid JSON.")


def parsed_stamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(result):
            raise ValueError
        return result.astimezone(dt_timezone.utc)
    except (AttributeError, ValueError, TypeError):
        error("Observation timestamps must be ISO datetimes with a timezone.")


def key(value, maximum=100):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1," + str(maximum) + r"}", value
    ):
        error("Invalid structured source key in synthetic sidecar.")
    return value


def pair(latitude, longitude, missing=False):
    if missing and latitude is None and longitude is None:
        return
    if (
        type(latitude) not in {float, int}
        or type(longitude) not in {float, int}
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        error(
            "Coordinates must be a complete finite latitude/longitude pair in range, or both missing."
        )


def require_list(value, limit, label):
    if not isinstance(value, list) or len(value) > limit:
        error(f"Invalid or oversized {label} array.")
    return value


def mapped_id(mapping, entity, source):
    try:
        return UUID(mapping["entities"][entity][source]["id"])
    except (KeyError, TypeError, ValueError, AttributeError):
        error("Clinical mapping is missing a valid source-to-database relationship.")


def load_package(dataset_dir, mapping_path):
    """Parse/validate all files without initializing or querying a database."""
    dataset_dir, mapping_path = Path(dataset_dir), Path(mapping_path)
    manifest_bytes, manifest_hash = read_file(dataset_dir / "manifest.json")
    manifest = read_json(manifest_bytes)
    if (
        not isinstance(manifest, dict)
        or manifest.get("synthetic") is not True
        or manifest.get("schema_version") != 1
    ):
        error("An explicitly synthetic schema version 1 manifest is required.")
    dataset_id = key(manifest.get("dataset_id"), 80)
    try:
        as_of, start = (
            date.fromisoformat(manifest["as_of"]),
            date.fromisoformat(manifest["observation_start"]),
        )
        if start > as_of or type(manifest["seed"]) is not int:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        error("Manifest dates or seed are invalid.")
    hashes, payloads = {}, {}
    for filename in (
        "dataset.json",
        "analytics_observations.jsonl",
        "evaluation_only_ground_truth.json",
    ):
        content, digest = read_file(dataset_dir / filename)
        expected = manifest.get("files", {}).get(filename, {})
        if expected.get("sha256") != digest or expected.get("bytes") != len(content):
            error("Manifest checksum or byte count does not match an input file.")
        hashes[filename] = digest
        payloads[filename] = content
    mapping_bytes, mapping_hash = read_file(mapping_path)
    mapping = read_json(mapping_bytes)
    if (
        not isinstance(mapping, dict)
        or mapping.get("synthetic") is not True
        or mapping.get("dataset_id") != dataset_id
        or mapping.get("dataset_sha256") != hashes["dataset.json"]
    ):
        error(
            "Clinical mapping must match the synthetic dataset identity and exact dataset hash."
        )
    hashes["clinical_mapping"] = mapping_hash
    dataset = read_json(payloads["dataset.json"])
    if (
        not isinstance(dataset, dict)
        or dataset.get("metadata", {}).get("dataset_id") != dataset_id
        or dataset.get("metadata", {}).get("synthetic") is not True
    ):
        error("Dataset and manifest identity do not match.")
    stations = {}
    for row in require_list(dataset.get("stations"), 200, "station"):
        if not isinstance(row, dict):
            error("Invalid station object.")
        sid = key(row.get("station_id"), 80)
        if (
            sid in stations
            or not isinstance(row.get("station_name"), str)
            or not 1 <= len(row["station_name"]) <= 150
        ):
            error("Duplicate or invalid canonical station.")
        lines = require_list(row.get("lines"), 3, "line membership")
        if (
            not lines
            or len(set(lines)) != len(lines)
            or set(lines) - {"Central", "Western", "Harbour"}
        ):
            error("Invalid station line memberships.")
        pair(row.get("latitude"), row.get("longitude"))
        stations[sid] = row
    if not stations:
        error("At least one canonical station is required.")
    patients, source_owner = {}, {}
    for row in require_list(dataset.get("patients"), 5000, "patient"):
        if not isinstance(row, dict):
            error("Invalid patient fixture object.")
        sid = key(row.get("source_id"))
        if sid in patients:
            error("Duplicate patient source key.")
        geography = row.get("geography", {})
        station = stations.get(geography.get("station_id"))
        if not station or set(geography.get("lines", [])) != set(station["lines"]):
            error("Patient geography must reference canonical station memberships.")
        lat, lon = (
            geography.get("synthetic_latitude"),
            geography.get("synthetic_longitude"),
        )
        pair(lat, lon, missing=True)
        expected_kind = (
            "not_generated" if lat is None else "simulated_station_catchment_point"
        )
        if geography.get("coordinate_kind") != expected_kind:
            error(
                "Coordinate provenance must distinguish simulated and missing points."
            )
        try:
            dob = date.fromisoformat(row["profile"]["date_of_birth"])
        except (KeyError, TypeError, ValueError):
            error("Patient age requires a valid fixture birth date.")
        patients[sid] = {
            "id": mapped_id(mapping, "patients", sid),
            "geography": geography,
            "dob": dob,
        }
        for category in ("records", "entries"):
            for source in require_list(row.get(category, []), 1000, "clinical source"):
                source_key = key(source.get("source_id"))
                if source_key in source_owner:
                    error("Clinical source keys must be unique.")
                source_owner[source_key] = {
                    "patient_key": sid,
                    "category": category,
                    "id": mapped_id(mapping, category, source_key),
                    "stamp": parsed_stamp(source.get("recorded_at")),
                }
    if (
        not patients
        or manifest.get("patient_count") != len(patients)
        or len({p["id"] for p in patients.values()}) != len(patients)
    ):
        error("Patient count or mapping uniqueness does not match the manifest.")
    observations, seen, diseases = [], set(), set()
    for line in payloads["analytics_observations.jsonl"].splitlines():
        if not line.strip():
            continue
        if len(observations) >= 50000:
            error("At most 50,000 synthetic observations are supported.")
        row = read_json(line)
        if not isinstance(row, dict) or set(row) != OBSERVATION_FIELDS:
            error("Sidecar contains missing or unsupported observation fields.")
        if row["dataset_id"] != dataset_id or row["is_synthetic"] is not True:
            error("Observation must belong to this explicitly synthetic batch.")
        patient_key, source_key = key(row["patient_key"]), key(row["record_key"])
        patient, source = patients.get(patient_key), source_owner.get(source_key)
        if not patient or not source or source["patient_key"] != patient_key:
            error("Observation source must belong to the mapped patient.")
        disease = row["disease_code"]
        if disease not in DISEASE_LABELS:
            error(
                "Observation disease code is not in the declared local disease vocabulary."
            )
        stamp = parsed_stamp(row["observed_at"])
        if not start <= stamp.date() <= as_of or stamp != source["stamp"]:
            error(
                "Observation timestamp must match its clinical source and dataset window."
            )
        geography = patient["geography"]
        if (
            row["station_id"] != geography["station_id"]
            or set(row["line_memberships"]) != set(geography["lines"])
            or row["synthetic_latitude"] != geography["synthetic_latitude"]
            or row["synthetic_longitude"] != geography["synthetic_longitude"]
            or row["coordinate_kind"] != geography["coordinate_kind"]
        ):
            error(
                "Observation geography must match its synthetic patient-area snapshot."
            )
        dob = patient["dob"]
        age = stamp.year - dob.year - ((stamp.month, stamp.day) < (dob.month, dob.day))
        if (
            row["age_at_observation"] != age
            or age < 18
            or row["age_band"] != f"{age // 10 * 10}s"
        ):
            error("Observation age band is inconsistent with the fixture.")
        episode = key(row["episode_key"], 150)
        import_key = source_key + ":" + disease
        if import_key in seen:
            error("Duplicate observation import key.")
        seen.add(import_key)
        diseases.add(disease)
        observations.append(
            {
                "patient_key": patient_key,
                "source": source,
                "disease": disease,
                "observed_at": stamp,
                "episode_key": episode,
                "import_key": import_key,
                "age_band": row["age_band"],
            }
        )
    truth = read_json(payloads["evaluation_only_ground_truth.json"])
    if (
        not isinstance(truth, dict)
        or truth.get("dataset_id") != dataset_id
        or truth.get("evaluation_only") is not True
    ):
        error("Ground truth must be separately marked evaluation-only for this batch.")
    truth_rows, labeled = [], set()
    for row in require_list(truth.get("labels"), 5000, "evaluation label"):
        if not isinstance(row, dict) or set(row) != {
            "patient_key",
            "primary_disease_code",
            "planted_group",
            "evaluation_only",
        }:
            error("Ground-truth fields are invalid.")
        sid, disease = key(row.get("patient_key")), row["primary_disease_code"]
        if (
            sid not in patients
            or sid in labeled
            or disease not in diseases
            or row["evaluation_only"] is not True
        ):
            error("Ground truth contains duplicate, foreign or unrecognized labels.")
        if not any(
            obs["patient_key"] == sid and obs["disease"] == disease
            for obs in observations
        ):
            error("Ground-truth primary disease must have a matching observation.")
        labeled.add(sid)
        truth_rows.append(
            {
                "patient_key": sid,
                "disease": disease,
                "planted_group": key(row["planted_group"]),
            }
        )
    if labeled != patients.keys():
        error(
            "Ground truth must contain exactly one primary label per synthetic patient."
        )
    return {
        "dataset_id": dataset_id,
        "manifest": manifest,
        "manifest_hash": manifest_hash,
        "input_hashes": hashes,
        "as_of": as_of,
        "observation_start": start,
        "stations": stations,
        "patients": patients,
        "observations": observations,
        "truth": truth_rows,
        "diseases": diseases,
    }


def import_package(package):
    """Write sidecars only; callers must select the guarded synthetic environment."""
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "LOCK TABLE analytics_datasetbatch IN SHARE ROW EXCLUSIVE MODE"
                )
        existing = (
            DatasetBatch.objects.select_for_update()
            .filter(key=package["dataset_id"])
            .first()
        )
        if existing:
            if (
                existing.manifest_hash != package["manifest_hash"]
                or existing.input_hashes != package["input_hashes"]
            ):
                error(
                    "This dataset key already exists with different input hashes; existing analytics are never overwritten."
                )
            return existing, False
        patients = package["patients"]
        patient_by_id = {
            obj.id: obj
            for obj in Patient.objects.filter(
                pk__in=[row["id"] for row in patients.values()]
            )
        }
        if len(patient_by_id) != len(patients):
            error(
                "Import the clinical fixture into this database before its analytics sidecars."
            )
        provenance = {}
        for event in SecurityEvent.objects.filter(
            user_id__in=[p.user_id for p in patient_by_id.values()],
            event="synthetic_dataset_import",
        ):
            provenance.setdefault(event.user_id, []).append(event.metadata)
        dataset_hash = package["input_hashes"]["dataset.json"]
        for sid, row in patients.items():
            if not any(
                meta.get("synthetic") is True
                and meta.get("dataset_id") == package["dataset_id"]
                and meta.get("source_id") == sid
                and meta.get("dataset_sha256") == dataset_hash
                for meta in provenance.get(patient_by_id[row["id"]].user_id, [])
            ):
                error(
                    "Clinical patient lineage is not marked as this exact synthetic import."
                )
        source_rows = {}
        for category, model in (("records", MedicalRecord), ("entries", ClinicalEntry)):
            ids = {
                row["source"]["id"]
                for row in package["observations"]
                if row["source"]["category"] == category
            }
            source_rows[category] = {
                row["id"]: row
                for row in model.objects.filter(pk__in=ids).values(
                    "id", "patient_id", "created_at"
                )
            }
        for row in package["observations"]:
            source = row["source"]
            actual = source_rows[source["category"]].get(source["id"])
            if (
                not actual
                or actual["patient_id"] != patients[row["patient_key"]]["id"]
                or actual["created_at"] != row["observed_at"]
            ):
                error(
                    "Clinical source relationship or historical timestamp does not match its sidecar."
                )
        manifest = package["manifest"]
        batch = DatasetBatch.objects.create(
            key=package["dataset_id"],
            synthetic=True,
            generator_version=manifest["generator_version"],
            seed=manifest["seed"],
            as_of=package["as_of"],
            observation_start=package["observation_start"],
            manifest_hash=package["manifest_hash"],
            dataset_hash=dataset_hash,
            input_hashes=package["input_hashes"],
            patient_count=len(patients),
            observation_count=len(package["observations"]),
        )
        station_rows = [
            StationArea(
                batch=batch,
                key=sid,
                name=row["station_name"],
                aliases=row.get("aliases", []),
                lines=row["lines"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                source_feature_ids=row.get("source_feature_ids", []),
                provenance={
                    "source_url": manifest.get("reference_metadata", {}).get(
                        "source_url", ""
                    ),
                    "anchor_method": row.get("anchor_method", ""),
                    "source_name": row.get("source_name", ""),
                    "license": manifest.get("reference_metadata", {}).get(
                        "source_license_id", ""
                    ),
                },
            )
            for sid, row in package["stations"].items()
        ]
        StationArea.objects.bulk_create(station_rows, batch_size=500)
        stations = {row.key: row for row in station_rows}
        area_rows = [
            PatientAreaObservation(
                batch=batch,
                patient_id=row["id"],
                source_key=sid,
                station=stations[row["geography"]["station_id"]],
                latitude=row["geography"]["synthetic_latitude"],
                longitude=row["geography"]["synthetic_longitude"],
                coordinate_source=row["geography"]["coordinate_kind"],
                valid_at=package["observation_start"],
            )
            for sid, row in patients.items()
        ]
        PatientAreaObservation.objects.bulk_create(area_rows, batch_size=500)
        areas = {row.source_key: row for row in area_rows}
        for code in sorted(package["diseases"]):
            obj, _ = DiseaseCode.objects.get_or_create(
                code=code, defaults={"label": DISEASE_LABELS[code]}
            )
            if obj.label != DISEASE_LABELS[code]:
                error("Existing local disease vocabulary does not match this import.")
        observations = []
        for row in package["observations"]:
            source = row["source"]
            observations.append(
                DiseaseObservation(
                    batch=batch,
                    patient_id=patients[row["patient_key"]]["id"],
                    area=areas[row["patient_key"]],
                    disease_id=row["disease"],
                    observed_at=row["observed_at"],
                    episode_key=row["episode_key"],
                    import_key=row["import_key"],
                    age_band=row["age_band"],
                    medical_record_id=source["id"]
                    if source["category"] == "records"
                    else None,
                    clinical_entry_id=source["id"]
                    if source["category"] == "entries"
                    else None,
                )
            )
        DiseaseObservation.objects.bulk_create(observations, batch_size=500)
        EvaluationTruth.objects.bulk_create(
            [
                EvaluationTruth(
                    batch=batch,
                    patient_id=patients[row["patient_key"]]["id"],
                    primary_disease_id=row["disease"],
                    planted_group=row["planted_group"],
                )
                for row in package["truth"]
            ],
            batch_size=500,
        )
        SecurityEvent.objects.create(
            event="synthetic_analytics_import",
            metadata={
                "synthetic": True,
                "dataset_id": batch.key,
                "manifest_hash": batch.manifest_hash,
                "patient_count": batch.patient_count,
                "observation_count": batch.observation_count,
            },
        )
        return batch, True
