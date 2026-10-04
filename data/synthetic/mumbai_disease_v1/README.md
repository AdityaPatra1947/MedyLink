# Mumbai synthetic disease expansion

This public fixture adds **3,000 fictional patients** to the unchanged 1,000-patient `../mumbai_stations_v1/` fixture. Together they reproduce the 4,000-patient demonstration. These files were generated offline from code and public station references. They were not exported from a database and contain no real patient data, passwords, secrets or active login credentials.

| File or derived entity | Count | Meaning |
| --- | ---: | --- |
| `patients.jsonl` | 3,000 | One patient profile, deterministic IDs and simulated station-area coordinates per line |
| `visits.jsonl` | 8,987 | One visit per line, linked by `patient_id`, with timestamp, synthetic measurements, symptoms and disease labels |
| Derived laboratory results | 25,596 | Nonmissing glucose, hemoglobin and platelet measurements from visits |
| Derived disease observations | 10,325 | Primary and optional secondary disease labels attached to visits |
| Reference station areas | 34 | Central, Western and Harbour areas, reused from the base fixture |

`manifest.json` records the schema, generator version `disease_v1`, seed `42`, date bounds, original fixture hash, row counts, disease counts and SHA-256/byte counts for both JSONL files. The history spans **31 October 2024–30 September 2026**. Coordinates are simulated nearby points, not household addresses or evidence of transmission. Missing measurements remain `null`. Synthetic disease patterns, seasonal weights, comorbidities and label noise are teaching assumptions, not clinical rules or evidence of diagnostic accuracy.

The importer derives application users, health IDs, clinical records, laboratory results and analytics links using the existing generation code. The added accounts retain **`is_active=False` and unusable passwords**. Their deterministic display names and test-only email addresses are generated during import. The original 1,013 base-fixture accounts keep their separate, locally generated test credentials. This expansion does not create credentials or enable patient sign-in.

## Reproduce the files

From the project root with Python available:

```console
python scripts/build_synthetic_expansion.py
```

On Windows without Python on PATH, use `.venv\Scripts\python.exe scripts/build_synthetic_expansion.py`. The builder uses only the standard library, the existing pure generator and the public base fixture. It never reads database settings or ignored local files. Rerunning it writes identical JSONL and manifest bytes. `--output PATH` writes a comparison build elsewhere. The original 1,000-patient files are never rewritten or copied into this directory.

## Import into the dedicated synthetic database

First migrate and import the base clinical fixture and its analytics sidecars using the [setup guide](../../../docs/ADMIN_ANALYTICS.md). Then run:

```console
npm run synthetic:manage -- import_synthetic_expansion
npm run synthetic:manage -- import_synthetic_expansion --apply
```

The default command validates offline without any database queries. It reproduces the expected canonical files and validates the full schema, every value and relationship, IDs, date range, counts, provenance and checksums. Changing data and rewriting its checksum does not bypass this validation. `--dataset-dir PATH` can select another reproducibly built expansion directory.

`--apply` requires the dedicated `synthetic_...` PostgreSQL settings, the matching original dataset hash, all 1,000 original mapped patients and the same station references. All writes occur in one transaction under the existing batch lock. Identity conflicts or an incomplete previous expansion are rejected without overwrites. Repeating an intact import is a no-op; it also recognizes patients previously added with `generate_synthetic_data --count 3000 --seed 42`. Both commands identify the same patients, so they must not be counted as separate cohorts.

Base patients, clinical records, credentials and original dataset manifest metadata remain unchanged. Patient-level data belongs in the isolated demonstration, not a production deployment. The [station source attribution](../../reference/STATION_SOURCES.md) applies to reused anchors.
