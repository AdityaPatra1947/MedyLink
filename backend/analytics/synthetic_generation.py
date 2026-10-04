"""Append-only, reproducible teaching data; the distributions are not clinical rules.

The original imported fixture and its manifest stay unchanged. Every additional
patient is linked to that synthetic batch, and every visit carries provenance.
The primary label has 5% independent noise; that label never generates features.
"""

import hashlib
import random
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid5

START = date(2024, 10, 31)
END = date(2026, 9, 30)
VERSION = "disease_v1"
BATCH_KEY = "mumbai_stations_v1"
NAMESPACE = UUID("062dbabc-e03f-45bd-a28c-61b1d8be8cee")
SYMPTOMS = ("fever", "cough", "joint_pain", "vomiting", "fatigue", "breathlessness", "headache", "rash")
WEIGHTS = {
    "DENGUE": 14, "INFLUENZA": 13, "HYPERTENSION": 12,
    "TYPE2_DIABETES": 12, "ASTHMA": 10, "ANEMIA": 10,
    "GASTROENTERITIS": 9, "HYPOTHYROIDISM": 8,
    "OSTEOARTHRITIS": 7, "MALARIA": 5,
}
SYMPTOM_CHANCES = {
    "DENGUE": {"fever": .97, "rash": .82, "joint_pain": .85, "headache": .75, "fatigue": .65},
    "INFLUENZA": {"fever": .89, "cough": .96, "fatigue": .60, "headache": .45},
    "HYPERTENSION": {"headache": .48, "fatigue": .25},
    "TYPE2_DIABETES": {"fatigue": .62, "headache": .20},
    "ASTHMA": {"breathlessness": .96, "cough": .70, "fatigue": .28},
    "ANEMIA": {"fatigue": .94, "breathlessness": .60, "headache": .32},
    "GASTROENTERITIS": {"vomiting": .96, "fever": .44, "fatigue": .60, "headache": .20},
    "HYPOTHYROIDISM": {"fatigue": .96, "joint_pain": .25},
    "OSTEOARTHRITIS": {"joint_pain": .97, "fatigue": .22},
    "MALARIA": {"fever": .97, "headache": .89, "fatigue": .81, "vomiting": .30},
}


def _rng(seed, key):
    digest = hashlib.sha256(f"{VERSION}:{seed}:{key}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def _id(seed, key):
    return str(uuid5(NAMESPACE, f"{VERSION}:{seed}:{key}"))


def _number(rng, mean, spread, low, high, digits=1):
    return round(min(high, max(low, rng.gauss(mean, spread))), digits)


def _base_measurements(rng, gender, age):
    return {
        "temperature_c": _number(rng, 36.8, .35, 35, 41),
        "systolic": int(_number(rng, 113 + max(0, age - 35) * .20, 10, 85, 205)),
        "diastolic": int(_number(rng, 73, 7, 52, 125)),
        "glucose_mg_dl": int(_number(rng, 96, 13, 65, 330)),
        "hemoglobin": _number(rng, 13 if gender == "female" else 14.4, 1, 6, 18),
        "spo2": _number(rng, 98, .8, 86, 100),
        "heart_rate_bpm": int(_number(rng, 76, 8, 48, 130)),
        "platelets": int(_number(rng, 255000, 50000, 35000, 450000, 0)),
    }


def _apply_pattern(values, disease, rng, *, secondary=False):
    # A secondary condition can soften/overlap the primary pattern, never erase it.
    pattern = {
        "DENGUE": {"temperature_c": (39.3, .55, 37.5, 41), "platelets": (82000, 27000, 30000, 180000), "heart_rate_bpm": (104, 10, 70, 135)},
        "INFLUENZA": {"temperature_c": (38.5, .55, 37, 40.5), "heart_rate_bpm": (95, 10, 65, 125)},
        "HYPERTENSION": {"systolic": (160, 14, 130, 205), "diastolic": (98, 9, 80, 125)},
        "TYPE2_DIABETES": {"glucose_mg_dl": (214, 38, 130, 350)},
        "ANEMIA": {"hemoglobin": (8.7, 1.15, 6, 11.8), "heart_rate_bpm": (96, 9, 68, 125)},
        "ASTHMA": {"spo2": (92, 2.0, 86, 97), "heart_rate_bpm": (98, 10, 68, 130)},
        "GASTROENTERITIS": {"temperature_c": (37.8, .65, 36, 40), "heart_rate_bpm": (94, 10, 65, 125)},
        "HYPOTHYROIDISM": {"temperature_c": (36.1, .35, 35, 37.2), "heart_rate_bpm": (59, 6, 45, 78)},
        "OSTEOARTHRITIS": {},
        "MALARIA": {"temperature_c": (39.3, .65, 37, 41), "hemoglobin": (10.5, 1.1, 7.5, 14), "platelets": (155000, 30000, 65000, 240000), "heart_rate_bpm": (104, 10, 70, 135)},
    }[disease]
    for key, (mean, spread, low, high) in pattern.items():
        sampled = _number(rng, mean, spread, low, high)
        value = .55 * values[key] + .45 * sampled if secondary else sampled
        values[key] = round(value, 1) if key in {"temperature_c", "hemoglobin", "spo2"} else int(value)


def _visit_dates(rng, disease, count):
    days = [START + timedelta(days=n) for n in range((END - START).days + 1)]
    peak = {"DENGUE": {7, 8, 9, 10}, "INFLUENZA": {6, 7, 8, 9, 12, 1}, "GASTROENTERITIS": {6, 7, 8, 9}, "MALARIA": {6, 7, 8, 9, 10}}.get(disease, set())
    weights = [4 if day.month in peak else 1 for day in days]
    chosen = set()
    while len(chosen) < count:
        chosen.add(rng.choices(days, weights=weights, k=1)[0])
    return sorted(chosen)


def generate_patients(count, seed, stations):
    """Pure helper returning JSON-compatible patient/visit dicts, with prefix stability.

    ``stations`` contains key/name/latitude/longitude dictionaries. Increasing
    count keeps earlier patients identical; each seed describes a separate set.
    IDs, measurements, dates and missing cells are reproducible, without Faker.
    """
    if type(count) is not int or not 1 <= count <= 5000:
        raise ValueError("count must be between 1 and 5000")
    if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise ValueError("seed must be a non-negative 64-bit integer")
    stations = sorted(stations, key=lambda row: row["key"])
    if not stations or len({row["key"] for row in stations}) != len(stations):
        raise ValueError("stations must have unique keys")
    disease_blocks, result = {}, []
    for index in range(count):
        block = index // 100
        if block not in disease_blocks:
            disease_blocks[block] = [code for code, weight in WEIGHTS.items() for _ in range(weight)]
            _rng(seed, f"block:{block}").shuffle(disease_blocks[block])
        disease = disease_blocks[block][index % 100]
        rng = _rng(seed, f"patient:{index}")
        label = rng.choice([code for code in WEIGHTS if code != disease]) if rng.random() < .05 else disease
        secondary = [rng.choice([code for code in WEIGHTS if code not in {disease, label}])] if rng.random() < .15 else []
        gender = "female" if rng.random() < (.76 if disease in {"ANEMIA", "HYPOTHYROIDISM"} else .49) else "male"
        lower = {"HYPERTENSION": 40, "TYPE2_DIABETES": 35, "OSTEOARTHRITIS": 50}.get(disease, 18)
        years = rng.randint(lower if rng.random() < .9 else 18, 82)
        dob = date(START.year - years, rng.randint(1, 12), rng.randint(1, 28))
        concentrated = {"DENGUE": {"KURLA", "VASHI", "ANDHERI"}, "INFLUENZA": {"BORIVALI", "GHATKOPAR", "NERUL"}}.get(disease, set())
        station = rng.choices(stations, weights=[12 if row["key"] in concentrated else 1 for row in stations], k=1)[0]
        dates = _visit_dates(rng, disease, rng.randint(2, 4))
        # Two boundary observations make the advertised full history explicit.
        if index == 0:
            dates[0] = START
        if index == 1:
            dates[-1] = END
        visits = []
        for number, observed in enumerate(dates):
            age = observed.year - dob.year - ((observed.month, observed.day) < (dob.month, dob.day))
            vitals = _base_measurements(rng, gender, age)
            _apply_pattern(vitals, disease, rng)
            for extra in secondary:
                _apply_pattern(vitals, extra, rng, secondary=True)
            symptoms = {key: int(rng.random() < SYMPTOM_CHANCES[disease].get(key, .04)) for key in SYMPTOMS}
            if secondary:
                for key, chance in SYMPTOM_CHANCES[secondary[0]].items():
                    symptoms[key] = max(symptoms[key], int(rng.random() < chance * .65))
            if rng.random() < .10:
                symptoms[rng.choice(SYMPTOMS)] = 1
            for key in vitals:
                if rng.random() < .05:
                    vitals[key] = None
            for key in symptoms:
                if rng.random() < .05:
                    symptoms[key] = None
            vitals.update({
                "synthetic": True, "generator": VERSION, "generation_seed": seed,
                "primary_disease_code": label, "secondary_disease_codes": secondary,
                "symptoms": symptoms, "glucose_context": "fasting",
            })
            if vitals["systolic"] is not None and vitals["diastolic"] is not None:
                vitals["blood_pressure"] = f"{vitals['systolic']}/{vitals['diastolic']}"
            if vitals["glucose_mg_dl"] is not None:
                vitals["blood_sugar"] = str(vitals["glucose_mg_dl"])
            visits.append({"id": _id(seed, f"record:{index}:{number}"), "observed_at": datetime.combine(observed, time(10, number), tzinfo=timezone.utc).isoformat(), "primary_disease_code": label, "secondary_disease_codes": secondary, "vitals": vitals})
        result.append({
            "id": _id(seed, f"patient:{index}"), "user_id": _id(seed, f"user:{index}"),
            "source_key": f"{VERSION}:{seed}:{index:05}", "ordinal": index,
            "date_of_birth": dob.isoformat(), "gender": gender,
            "station_key": station["key"], "station_name": station["name"],
            "latitude": round(station["latitude"] + rng.uniform(-.007, .007), 6),
            "longitude": round(station["longitude"] + rng.uniform(-.007, .007), 6),
            "visits": visits,
        })
    return result


def _historical_bulk_create(model, objects):
    """Restore supplied historical dates after Django's auto_now_add hook."""
    if not objects:
        return
    dates = [row.created_at for row in objects]
    model.objects.bulk_create(objects, batch_size=500)
    for row, stamp in zip(objects, dates, strict=True):
        row.created_at = stamp
    model.objects.bulk_update(objects, ["created_at"], batch_size=500)


def append_synthetic_patients(count=3000, seed=42, batch_key=BATCH_KEY, *, fixture=None):
    """Guarded database entry point; repeated seed/count is a no-op, not a reset."""
    from accounts.models import SecurityEvent, User
    from clinic.management.commands.import_synthetic_dataset import Command as Importer
    from clinic.models import LabResult, MedicalRecord, Patient, ProviderApplication
    from django.core.management.base import CommandError
    from django.db import transaction
    from django.db.models import Q

    from .importing import DISEASE_LABELS
    from .models import (
        DatasetBatch,
        DiseaseCode,
        DiseaseObservation,
        PatientAreaObservation,
    )

    Importer().require_target()
    with transaction.atomic():
        try:
            batch = DatasetBatch.objects.select_for_update().get(key=batch_key, synthetic=True)
        except DatasetBatch.DoesNotExist:
            raise CommandError("Import the Mumbai synthetic fixture and analytics sidecars first.") from None
        stations = list(batch.stations.order_by("key"))
        if len(stations) != 34:
            raise CommandError("The existing synthetic batch must contain the same 34 Mumbai stations.")
        if fixture is not None:
            from .synthetic_fixture import validate_existing, validate_target

            validate_target(fixture, batch, stations)
            generated = fixture["patients"]
        else:
            try:
                generated = generate_patients(count, seed, [{"key": row.key, "name": row.name, "latitude": row.latitude, "longitude": row.longitude} for row in stations])
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
        existing_areas = dict(batch.areas.filter(source_key__startswith=f"{VERSION}:{seed}:").values_list("source_key", "patient_id"))
        existing = set(existing_areas)
        if fixture is not None:
            validate_existing(fixture, batch, existing_areas)
        pending = [row for row in generated if row["source_key"] not in existing]
        summary = {"synthetic": True, "generator": VERSION, "seed": seed, "requested": count, "created_patients": len(pending), "existing_patients": count - len(pending), "created_visits": 0, "created_labs": 0}
        if not pending:
            return summary
        if batch.areas.count() + len(pending) > 5000:
            raise CommandError("This ML demonstration supports at most 5,000 mapped patients; reduce --count.")
        doctor_ids = list(User.objects.filter(role="doctor", is_active=True, pk__in=ProviderApplication.objects.filter(is_current=True, status="approved").values("provider_id")).order_by("id").values_list("id", flat=True))
        if not doctor_ids:
            raise CommandError("The synthetic database needs at least one approved synthetic doctor.")
        users, patients, areas, records, labs, observations = [], [], [], [], [], []
        station_by_key = {row.key: row for row in stations}
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        for row in pending:
            uid = UUID(row["user_id"])
            suffix = "".join(alphabet[(uid.int >> (5 * pos)) & 31] for pos in range(7))
            first = datetime.fromisoformat(row["visits"][0]["observed_at"])
            users.append(User(id=uid, account_id=f"P-{suffix}", email=f"synthetic-{seed}-{row['ordinal']:05}@patients.medylink.invalid", name=f"Simulated Patient {seed}-{row['ordinal'] + 1:05}", role="patient", password="!", is_active=False, email_verified_at=first, created_at=first, privacy_version="synthetic-disease-v1"))
            patients.append(Patient(id=row["id"], user_id=uid, health_id="ML-S" + UUID(row["id"]).hex[:20].upper(), card_locator=uuid5(NAMESPACE, row["id"] + ":card").hex, date_of_birth=date.fromisoformat(row["date_of_birth"]), gender=row["gender"], address=f"Simulated station area: {row['station_name']}", created_at=first))
            area = PatientAreaObservation(batch=batch, patient_id=row["id"], source_key=row["source_key"], station=station_by_key[row["station_key"]], latitude=row["latitude"], longitude=row["longitude"], coordinate_source="synthetic_disease_v1", valid_at=START)
            areas.append(area)
            doctor = doctor_ids[row["ordinal"] % len(doctor_ids)]
            for visit in row["visits"]:
                stamp = datetime.fromisoformat(visit["observed_at"])
                labels = [visit["primary_disease_code"], *visit["secondary_disease_codes"]]
                symptoms = [key.replace("_", " ") for key, flag in visit["vitals"]["symptoms"].items() if flag == 1]
                records.append(MedicalRecord(id=visit["id"], patient_id=row["id"], doctor_id=doctor, created_at=stamp, complaint=", ".join(symptoms).capitalize() or "Follow-up measurement review", diagnosis="; ".join(DISEASE_LABELS[code] for code in labels), notes="Simulated training consultation; observations generated for this visit. Not a real patient or a clinical recommendation.", vitals=visit["vitals"]))
                for key, name, unit, low, high in (("glucose_mg_dl", "Fasting glucose", "mg/dL", 70, 99), ("hemoglobin", "Hemoglobin", "g/dL", 12 if row["gender"] == "female" else 13, 16 if row["gender"] == "female" else 17), ("platelets", "Platelet count", "/uL", 150000, 450000)):
                    value = visit["vitals"][key]
                    if value is not None:
                        labs.append(LabResult(id=uuid5(NAMESPACE, visit["id"] + ":" + key), patient_id=row["id"], recorded_by_id=doctor, name=name, value=value, unit=unit, reference_low=low, reference_high=high, measured_at=stamp, created_at=stamp))
                age = stamp.year - patients[-1].date_of_birth.year - ((stamp.month, stamp.day) < (patients[-1].date_of_birth.month, patients[-1].date_of_birth.day))
                for code in labels:
                    observations.append(DiseaseObservation(batch=batch, patient_id=row["id"], area=area, disease_id=code, observed_at=stamp, episode_key=visit["id"], import_key=f"{VERSION}:{visit['id']}:{code}", age_band=f"{age // 10 * 10}s", medical_record_id=visit["id"]))
        if fixture is not None:
            if (User.objects.filter(Q(pk__in=[row.pk for row in users]) | Q(email__in=[row.email for row in users]) | Q(account_id__in=[row.account_id for row in users])).exists()
                    or Patient.objects.filter(Q(pk__in=[row.pk for row in patients]) | Q(health_id__in=[row.health_id for row in patients]) | Q(card_locator__in=[row.card_locator for row in patients])).exists()
                    or MedicalRecord.objects.filter(pk__in=[row.pk for row in records]).exists()
                    or LabResult.objects.filter(pk__in=[row.pk for row in labs]).exists()
                    or batch.observations.filter(import_key__in=[row.import_key for row in observations]).exists()):
                raise CommandError("Expansion identities conflict with existing records; no records were changed.")
        User.objects.bulk_create(users, batch_size=500)
        _historical_bulk_create(Patient, patients)
        PatientAreaObservation.objects.bulk_create(areas, batch_size=500)
        _historical_bulk_create(MedicalRecord, records)
        _historical_bulk_create(LabResult, labs)
        existing_codes = set(DiseaseCode.objects.values_list("code", flat=True))
        DiseaseCode.objects.bulk_create([DiseaseCode(code=code, label=DISEASE_LABELS[code]) for code in WEIGHTS if code not in existing_codes])
        DiseaseObservation.objects.bulk_create(observations, batch_size=500)
        summary.update(created_visits=len(records), created_labs=len(labs))
        provenance = {"fixture_id": fixture["manifest"]["fixture_id"], "fixture_manifest_sha256": fixture["manifest_hash"]} if fixture is not None else {}
        SecurityEvent.objects.create(event="synthetic_disease_generation", metadata={**summary, **provenance, "dataset_id": batch.key, "history_start": START.isoformat(), "history_end": END.isoformat()})
        return summary
