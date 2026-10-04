"""Generate fictional application fixtures and separate analytics inputs; no DB/network.

Clinical values and frequency choices are simulation parameters, not medical guidance.
All credentials are random, test-only, and written exclusively under ignored .local/.
"""

import argparse
import hashlib
import json
import math
import random
import secrets
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
SEED = 20260929
DOMAIN = "synthetic.medylink.test"
DISEASES = {
    "DENGUE": ("Dengue", False),
    "MALARIA": ("Malaria", False),
    "INFLUENZA": ("Influenza", False),
    "GASTROENTERITIS": ("Gastroenteritis", False),
    "TYPE2_DIABETES": ("Type 2 diabetes", True),
    "HYPERTENSION": ("Hypertension", True),
    "ASTHMA": ("Asthma", True),
    "ANEMIA": ("Anemia", True),
    "OSTEOARTHRITIS": ("Osteoarthritis", True),
    "HYPOTHYROIDISM": ("Hypothyroidism", True),
    "NO_RECORDED_DISEASE": ("General consultation; no disease recorded", False),
}
MALE = "Aarav Aditya Akash Akshay Aman Amit Anand Aniket Anirudh Arjun Atharva Avinash Bharat Chirag Deepak Dev Dhruv Gaurav Harish Harsh Hemant Hrishikesh Ishaan Jay Kabir Karan Kunal Manish Mayank Mihir Milind Mohan Nikhil Nilesh Nitin Omkar Pranav Pratik Rahul Raj Rajesh Rakesh Rohan Rohit Sachin Sameer Sandeep Sanjay Shreyas Siddharth Soham Sumit Suresh Tanmay Tejas Uday Varun Vedant Vijay Vikram Vinay Vishal Yash Yusuf Zubin".split()
FEMALE = "Aditi Aisha Akanksha Amrita Ananya Anjali Ankita Anushka Aparna Archana Arya Asmita Bhavana Chaitali Deepa Devika Dhara Diya Esha Farah Gauri Geeta Harini Isha Jaya Juhi Kavita Khushi Kriti Leena Madhavi Mahima Manasi Maya Meera Megha Mira Nandini Neha Nidhi Nikita Nisha Pooja Prachi Pranali Priya Radha Rashi Rhea Ritu Riya Sakshi Sanika Sara Shreya Shruti Simran Sneha Sonal Srishti Sujata Swati Tanvi Trisha Vaidehi Vidya Zoya".split()
SURNAMES = "Agrawal Ansari Apte Arora Bansal Bendre Bhandari Bhat Bhatt Bhosale Bose Chandra Chavan Chitnis Dalvi Desai Deshmukh Deshpande Dey Fernandes Gadgil Gandhi Ghosh Gokhale Gupta Iyer Jadhav Jain Joshi Kamat Kapoor Karandikar Khan Khanna Kulkarni Kumar Lobo Mahajan Malhotra Mane Mehta Menon Mishra Mohanty More Mukherjee Naik Nair Nambiar Patil Patel Pathak Pawar Pradhan Rao Rane Raut Reddy Roy Saha Salvi Sawant Shah Shaikh Sharma Shinde Singh Soman Soni Srinivasan Subramanian Thakur Thomas Trivedi Vaidya Verma Wagh Yadav".split()
# Six intentionally planted groups, including three spatial groups per disease.
# These labels belong to evaluation-only output, never to an ML feature matrix.
SCENARIOS = [
    ("SIM_DENGUE_KURLA", "DENGUE", "KURLA", 50),
    ("SIM_DENGUE_ANDHERI", "DENGUE", "ANDHERI", 50),
    ("SIM_DENGUE_VASHI", "DENGUE", "VASHI", 50),
    ("SIM_FLU_GHATKOPAR", "INFLUENZA", "GHATKOPAR", 35),
    ("SIM_FLU_BORIVALI", "INFLUENZA", "BORIVALI", 35),
    ("SIM_FLU_NERUL", "INFLUENZA", "NERUL", 35),
]


def age_on(dob, when):
    return when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))


def stamp(day, hour=9):
    return datetime.combine(day, time(hour), timezone.utc).isoformat().replace("+00:00", "Z")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def jitter(rng, station, planted):
    # A synthetic point, not a home geocode; no land/residential-boundary claim.
    radius = rng.uniform(0.04, 0.35) if planted else rng.uniform(0.15, 1.2)
    angle = rng.uniform(0, math.tau)
    lat = station["latitude"] + radius * math.cos(angle) / 111.195
    lon = station["longitude"] + radius * math.sin(angle) / (
        111.195 * math.cos(math.radians(station["latitude"]))
    )
    return round(lat, 5), round(lon, 5)


def make_vitals(rng, age, code):
    # Overlapping, bounded simulation distributions, deliberately not diagnostic rules.
    systolic = round(max(92, min(172, rng.gauss(116 + max(0, age - 40) * 0.3 + (12 if code == "HYPERTENSION" else 0), 13))))
    diastolic = round(max(58, min(106, rng.gauss(76 + (6 if code == "HYPERTENSION" else 0), 9))))
    vitals = {
        "systolic": max(systolic, diastolic + 15),
        "diastolic": diastolic,
        "temperature_c": round(rng.uniform(36.3, 39.1) if code in {"DENGUE", "MALARIA", "INFLUENZA"} else rng.uniform(36.2, 37.7), 1),
        "heart_rate_bpm": rng.randint(60, 110),
        "weight_kg": round(rng.uniform(44, 106), 1),
        "height_cm": rng.randint(148, 188),
    }
    if rng.random() > 0.14:
        vitals["glucose_mg_dl"] = round(max(65, min(240, rng.gauss(133 if code == "TYPE2_DIABETES" else 104, 27))))
        vitals["glucose_context"] = rng.choice(["fasting", "random"])
    return vitals


def create_data(stations, dataset_id, seed, as_of):
    rng = random.Random(seed)
    station_map = {s["station_id"]: s for s in stations}
    names = [(f"{first} {last}", gender) for gender, firsts in [("male", MALE), ("female", FEMALE)] for first in firsts for last in SURNAMES]
    rng.shuffle(names)
    names = names[:1000]
    plan = [(label, code, station) for label, code, station, size in SCENARIOS for _ in range(size)]
    # Put every remaining station in the plan before random choices ensure coverage.
    plan += [("BACKGROUND", None, stations[i % len(stations)]["station_id"]) for i in range(1000 - len(plan))]
    rng.shuffle(plan)
    providers = []
    for i, role in enumerate(["doctor"] * 9 + ["pharmacist"] * 3 + ["admin"]):
        sid = f"DOC{i + 1:03}" if role == "doctor" else f"PHARM{i - 8:03}" if role == "pharmacist" else "ADMIN001"
        station = stations[i % len(stations)]
        provider = {
            "source_id": sid,
            "user": {"email": f"{sid.lower()}@{DOMAIN}", "name": f"Synthetic {role.title()} {i + 1:02}", "role": role, "created_at": stamp(as_of - timedelta(days=370))},
        }
        if role != "admin":
            provider["application"] = {
                "registration_number": f"SYNTHETIC-NOT-A-LICENSE-{sid}",
                "registering_body": "SYNTHETIC DEMO COUNCIL - NOT A REGULATOR",
                "specialty": "General practice (demo)",
                "qualification": "Synthetic credential; no professional claim",
                "practice_address": f"Synthetic demo practice near {station['station_name']} station",
                "shop_name": f"Synthetic Pharmacy {sid}" if role == "pharmacist" else "",
                "shop_license": f"SYNTHETIC-SHOP-{sid}" if role == "pharmacist" else "",
                "shop_license_expires": (as_of + timedelta(days=365)).isoformat() if role == "pharmacist" else None,
                "valid_until": stamp(as_of + timedelta(days=365)),
                "reason": "Synthetic approval only in isolated demo database",
                "evidence_reviewed": "Generated fixture; no genuine professional credential was verified",
            }
        providers.append(provider)

    patients, analytics, truth = [], [], []
    chronic_codes = [code for code, (_, chronic) in DISEASES.items() if chronic]
    for i, ((name, gender), (label, scenario_code, station_id)) in enumerate(zip(names, plan), 1):
        sid = f"PAT{i:04}"
        station = station_map[station_id]
        low, high = rng.choices([(18, 29), (30, 44), (45, 59), (60, 74), (75, 85)], [22, 28, 25, 18, 7])[0]
        target_age = rng.randint(low, high)
        dob = date(as_of.year - target_age, rng.randint(1, 12), rng.randint(1, 28))
        if age_on(dob, as_of) != target_age:
            dob = dob.replace(year=dob.year - 1)
        age = age_on(dob, as_of)
        earliest = max(as_of - timedelta(days=364), dob.replace(year=dob.year + 18))
        codes = list(DISEASES)
        weights = [6, 6, 7, 10, 15 if age >= 40 else 5, 16 if age >= 40 else 5, 10, 8, 11 if age >= 50 else 2, 6, 12]
        primary = scenario_code or rng.choices(codes, weights)[0]
        chronic = DISEASES[primary][1]
        extra = rng.choice([code for code in chronic_codes if code != primary]) if primary != "NO_RECORDED_DISEASE" and rng.random() < 0.22 else None
        lat, lon = jitter(rng, station, label != "BACKGROUND")
        if label == "BACKGROUND" and rng.random() < 0.035:
            lat, lon = None, None  # Explicit missingness for exclusion handling.
        doctor_sid = f"DOC{1 + (i - 1) % 9:03}"
        index_date = as_of - timedelta(days=rng.randint(4, 19)) if scenario_code else earliest + timedelta(days=rng.randrange(max(1, (as_of - earliest).days - 20)))
        index_date = max(earliest, min(index_date, as_of))
        follow_date = max(index_date, as_of - timedelta(days=rng.randint(0, 25))) if chronic else min(as_of, index_date + timedelta(days=rng.randint(4, 21)))
        record_dates = sorted(set([index_date, follow_date]))
        if len(record_dates) == 2 and (follow_date - index_date).days > 50 and rng.random() < 0.55:
            record_dates.insert(1, index_date + (follow_date - index_date) // 2)
        if len(record_dates) == 1 and index_date < as_of:
            record_dates.append(min(as_of, index_date + timedelta(days=1)))
        has_allergy = rng.random() < 0.16
        allergy = rng.choice(["Pollen", "Peanuts", "Penicillin", "Dust mites", "Latex"]) if has_allergy else None
        status = "reported" if allergy else ("unknown" if rng.random() < 0.17 else "none_known")
        user_created = max(dob.replace(year=dob.year + 18), index_date - timedelta(days=7))
        patient = {
            "source_id": sid,
            "is_synthetic": True,
            "user": {"email": f"patient{i:04}@{DOMAIN}", "name": name, "phone": "", "created_at": stamp(user_created, 7)},
            "profile": {
                "date_of_birth": dob.isoformat(), "gender": gender if rng.random() > 0.025 else "prefer_not_to_say", "phone": "",
                "address": f"SYNTHETIC station catchment near {station['station_name']}, {station['city']}, Maharashtra, India; not a household address",
                "blood_group": rng.choice(["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-", "unknown"]),
                "emergency_contact": f"Synthetic relative for {sid}; telephone not supplied",
                "allergy_status": status,
            },
            "geography": {"station_id": station_id, "lines": station["lines"], "city": station["city"], "state": "Maharashtra", "country": "India", "synthetic_latitude": lat, "synthetic_longitude": lon, "coordinate_kind": "simulated_station_catchment_point" if lat is not None else "not_generated"},
            "age_as_of": age, "age_reference_date": as_of.isoformat(),
            "records": [], "entries": [], "labs": [], "prescriptions": [], "adherence": [],
        }
        for j, recorded in enumerate(record_dates, 1):
            record_id = f"{sid}-VISIT{j:02}"
            patient["records"].append({
                "source_id": record_id, "doctor_source_id": doctor_sid, "recorded_at": stamp(recorded), "disease_code": primary,
                "complaint": "Synthetic initial consultation" if j == 1 else "Synthetic follow-up consultation",
                "diagnosis": DISEASES[primary][0],
                "notes": "SYNTHETIC DATA: fictional consultation for software testing. Disease label is assigned by the generator, not inferred from vitals. Not medical advice.",
                "vitals": make_vitals(rng, age_on(dob, recorded), primary),
            })
            analytics.append({
                "dataset_id": dataset_id, "is_synthetic": True, "patient_key": sid,
                "record_key": record_id, "episode_key": f"{sid}-PRIMARY", "disease_code": primary,
                "observed_at": stamp(recorded), "age_at_observation": age_on(dob, recorded),
                "age_band": f"{age_on(dob, recorded) // 10 * 10}s",
                "station_id": station_id, "line_memberships": station["lines"],
                "synthetic_latitude": lat, "synthetic_longitude": lon,
                "coordinate_kind": patient["geography"]["coordinate_kind"],
            })
        for code in ([primary] if chronic else []) + ([extra] if extra else []):
            patient["entries"].append({"source_id": f"{sid}-CONDITION-{code}", "kind": "condition", "name": DISEASES[code][0], "notes": "Synthetic chronic condition; not a clinical assessment", "source": "clinician_recorded", "author_source_id": doctor_sid, "recorded_at": stamp(index_date)})
        if allergy:
            patient["entries"].append({"source_id": f"{sid}-ALLERGY", "kind": "allergy", "name": allergy, "notes": "Synthetic patient-reported allergy; not independently confirmed", "source": "patient_reported", "author_source_id": sid, "recorded_at": stamp(index_date)})
        if extra:
            analytics.append({"dataset_id": dataset_id, "is_synthetic": True, "patient_key": sid, "record_key": f"{sid}-CONDITION-{extra}", "episode_key": f"{sid}-SECONDARY", "disease_code": extra, "observed_at": stamp(index_date), "age_at_observation": age_on(dob, index_date), "age_band": f"{age_on(dob, index_date) // 10 * 10}s", "station_id": station_id, "line_memberships": station["lines"], "synthetic_latitude": lat, "synthetic_longitude": lon, "coordinate_kind": patient["geography"]["coordinate_kind"]})
        for lab_name, unit, value in [("Glucose (synthetic)", "mg/dL", rng.uniform(75, 190)), ("Hemoglobin (synthetic)", "g/dL", rng.uniform(10, 16))]:
            if rng.random() < 0.65:
                patient["labs"].append({"source_id": f"{sid}-LAB{len(patient['labs']) + 1:02}", "doctor_source_id": doctor_sid, "name": lab_name, "value": f"{value:.2f}", "unit": unit, "measured_at": stamp(record_dates[-1], 8)})
        if primary != "NO_RECORDED_DISEASE" and rng.random() < 0.78:
            issued = record_dates[-1]
            patient["prescriptions"].append({
                "source_id": f"{sid}-RX01", "doctor_source_id": doctor_sid, "record_source_id": patient["records"][-1]["source_id"],
                "issued_at": stamp(issued, 10), "valid_until": stamp(issued + timedelta(days=30), 10),
                "notes": "SYNTHETIC workflow placeholder. No genuine medicine or treatment is prescribed.",
                "items": [{"medicine": "Synthetic Demo Item A - NOT A REAL MEDICINE", "dosage": "Demo instructions only; do not administer", "instructions": "Quantity exists to exercise the pharmacy workflow; not treatment advice", "quantity": f"{rng.choice([6, 10, 14, 20])}.000", "unit": "demo_unit"}],
            })
            # Only dates after the synthetic prescription; no inferred adherence.
            start = max(issued, as_of - timedelta(days=13))
            if chronic and (as_of - issued).days <= 29:
                for offset in range((as_of - start).days + 1):
                    logged = start + timedelta(days=offset)
                    if rng.random() < 0.1:
                        continue  # An absent log is unknown, not a missed dose.
                    patient["adherence"].append({"source_id": f"{sid}-DOSE-{logged}", "date": logged.isoformat(), "scheduled_doses": 2, "taken_doses": rng.choices([0, 1, 2], [5, 15, 80])[0]})
        patients.append(patient)
        truth.append({"patient_key": sid, "primary_disease_code": primary, "planted_group": label, "evaluation_only": True})

    metadata = {
        "schema_version": 1, "generator_version": VERSION, "dataset_id": dataset_id,
        "synthetic": True, "seed": seed, "as_of": as_of.isoformat(), "patient_count": 1000,
        "observation_start": (as_of - timedelta(days=364)).isoformat(),
        "geography_scope": "Selected Mumbai Metropolitan Region station catchments: Central, Western, Harbour",
        "contact_policy": "Reserved .test emails; phone fields empty; no household addresses",
        "clinical_policy": "Invented labels and overlapping observations, no clinical validation; prescription placeholders only",
        "classification": "SYNTHETIC DEMO ONLY - NOT OBSERVED PATIENT DATA",
    }
    return {"metadata": metadata, "stations": stations, "providers": providers, "patients": patients}, analytics, truth


def validate(dataset, analytics, truth):
    patients = dataset["patients"]
    assert len(patients) == 1000
    for values in [[p["source_id"] for p in patients], [p["user"]["name"] for p in patients], [p["user"]["email"] for p in patients]]:
        assert len(set(values)) == 1000
    station_map = {s["station_id"]: s for s in dataset["stations"]}
    assert set(p["geography"]["station_id"] for p in patients) == set(station_map)
    assert station_map["DADAR"]["lines"] == ["Central", "Western"] or set(station_map["DADAR"]["lines"]) == {"Central", "Western"}
    assert "Harbour" not in station_map["THANE"]["lines"]
    as_of = date.fromisoformat(dataset["metadata"]["as_of"])
    patient_ids = {p["source_id"] for p in patients}
    for patient in patients:
        dob = date.fromisoformat(patient["profile"]["date_of_birth"])
        assert 18 <= age_on(dob, as_of) <= 85
        assert age_on(dob, as_of) == patient["age_as_of"]
        dates = [date.fromisoformat(r["recorded_at"][:10]) for r in patient["records"]]
        assert dates == sorted(dates)
        assert all(dob < d <= as_of and age_on(dob, d) >= 18 for d in dates)
        for r in patient["records"]:
            assert r["vitals"]["systolic"] > r["vitals"]["diastolic"]
        for row in patient["adherence"]:
            assert as_of - timedelta(days=29) <= date.fromisoformat(row["date"]) <= as_of
            assert 0 <= row["taken_doses"] <= row["scheduled_doses"]
    blocked = {"name", "email", "password", "phone", "address", "planted_group", "diagnosis", "notes", "date_of_birth"}
    for row in analytics:
        assert not (blocked & set(row))
        assert row["patient_key"] in patient_ids
        assert set(row["line_memberships"]) == set(station_map[row["station_id"]]["lines"])
        lat, lon = row["synthetic_latitude"], row["synthetic_longitude"]
        assert (lat is None and lon is None) or (18.8 <= lat <= 19.4 and 72.7 <= lon <= 73.3)
    assert len(truth) == 1000 and len({t["patient_key"] for t in truth}) == 1000
    return {
        "status": "passed", "patient_count": len(patients), "unique_names": 1000,
        "station_count": len(station_map), "provider_count": len(dataset["providers"]),
        "age_min": min(p["age_as_of"] for p in patients), "age_max": max(p["age_as_of"] for p in patients),
        "medical_records": sum(len(p["records"]) for p in patients),
        "clinical_entries": sum(len(p["entries"]) for p in patients),
        "lab_results": sum(len(p["labs"]) for p in patients),
        "prescriptions": sum(len(p["prescriptions"]) for p in patients),
        "adherence_logs": sum(len(p["adherence"]) for p in patients),
        "analytics_observations": len(analytics),
        "missing_coordinate_patients": sum(p["geography"]["synthetic_latitude"] is None for p in patients),
        "primary_disease_patient_counts": dict(sorted(Counter(p["records"][0]["disease_code"] for p in patients).items())),
        "station_patient_counts": dict(sorted(Counter(p["geography"]["station_id"] for p in patients).items())),
        "line_membership_patient_counts_non_additive": dict(sorted(Counter(line for p in patients for line in p["geography"]["lines"]).items())),
        "planted_groups": dict(sorted(Counter(t["planted_group"] for t in truth).items())),
        "checks": ["exactly_1000_unique_patients_names_emails", "adult_ages_at_observation", "sourced_station_references", "interchange_membership", "no_identity_or_credentials_in_analytics", "dates_not_future", "valid_dose_counts", "vital_ordering", "patient_level_truth_keys"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 9, 29))
    parser.add_argument("--dataset-id", default="mumbai_stations_v1")
    args = parser.parse_args()
    if not args.dataset_id.replace("_", "").isalnum():
        parser.error("dataset-id must contain letters, numbers and underscores only")
    output = ROOT / "data" / "synthetic" / args.dataset_id
    private = ROOT / ".local" / "synthetic" / args.dataset_id
    if output.exists() or private.exists():
        parser.error("Dataset output already exists. Use a NEW --dataset-id; existing data/passwords will not be overwritten.")
    reference_path = ROOT / "data" / "reference" / "mumbai_stations.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    dataset, analytics, truth = create_data(reference["stations"], args.dataset_id, args.seed, args.as_of)
    report = validate(dataset, analytics, truth)
    accounts = []
    for entity in dataset["providers"] + dataset["patients"]:
        user = entity["user"]
        accounts.append({"source_id": entity["source_id"], "role": user.get("role", "patient"), "name": user["name"], "email": user["email"], "password": "Demo!" + secrets.token_urlsafe(20)})
    assert len({a["password"] for a in accounts}) == len(accounts)
    credentials = {"dataset_id": args.dataset_id, "synthetic": True, "warning": "TEST ONLY. These logins work only after import into a dedicated synthetic database. Never reuse these passwords.", "accounts": accounts}
    write_json(private / "credentials.json", credentials)
    (private / "credentials.json").chmod(0o600)
    write_json(output / "dataset.json", dataset)
    with (output / "analytics_observations.jsonl").open("x", encoding="utf-8", newline="\n") as handle:
        for row in analytics:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    write_json(output / "evaluation_only_ground_truth.json", {"dataset_id": args.dataset_id, "evaluation_only": True, "labels": truth, "scenarios": [{"label": label, "disease_code": code, "station_id": station, "size": size} for label, code, station, size in SCENARIOS]})
    write_json(output / "validation_report.json", report)
    manifest = {
        **dataset["metadata"], "reference_metadata": reference["metadata"],
        "generator_sha256": digest(Path(__file__)), "station_reference_sha256": digest(reference_path),
        "files": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in sorted(output.iterdir()) if p.is_file()},
        "credentials": "Excluded from shareable files; stored under ignored .local/synthetic/<dataset_id>/credentials.json",
        "generation_reproducibility": "Public dataset bytes repeat for the same generator/reference/seed/date; credentials are cryptographically random each run.",
    }
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output": str(output), "credentials_file": str(private / "credentials.json"), "patient_count": report["patient_count"], "medical_records": report["medical_records"], "station_count": report["station_count"], "validation": report["status"]}, indent=2))


if __name__ == "__main__":
    main()
