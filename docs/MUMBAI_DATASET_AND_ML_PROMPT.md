# Mumbai station dataset and admin ML implementation prompt

Prepared for the current MedyLink code on **29 September 2026**.

**Phase 1 implementation:** the persistent import, administrator dashboard, geographic DBSCAN and evaluation workflow are now implemented. Use [the admin analytics guide](ADMIN_ANALYTICS.md) for current setup and operation. The implementation prompt later in this document is retained as the original design brief.

The requested dataset has been generated: **1,000 fictional adults aged 18–85**, with unique names and email/password pairs, across **34 selected station areas** on the **Central, Western, and Harbour** lines. This is a simulation for application development and ML demonstrations. It contains no actual patient records or observed disease cases.

The user's new request adds admin ML analytics to the project. It supersedes the original specification's exclusion of ML for this scope. It does not request automated diagnosis, treatment recommendations, an LLM, or a claim that station clusters are real outbreaks.

## 1. Generated files

Paths below are relative to the repository root.

| File | Purpose |
| --- | --- |
| `data/synthetic/mumbai_stations_v1/dataset.json` | Application fixture: 1,000 patient identities/profiles, related records, allergies/conditions, labs, placeholder prescriptions, adherence logs, and 13 supporting accounts |
| `.local/synthetic/mumbai_stations_v1/credentials.json` | Private local login list: source ID, name, role, email, unique random test password; excluded from Git |
| `data/synthetic/mumbai_stations_v1/analytics_observations.jsonl` | 2,394 pseudonymous observation rows; excludes names, email, password, phone, DOB, address, and clinical free text |
| `data/synthetic/mumbai_stations_v1/evaluation_only_ground_truth.json` | Hidden-from-training scenario labels for recovering planted synthetic groups |
| `data/synthetic/mumbai_stations_v1/validation_report.json` | Counts, age range, missingness, station coverage, and checks performed |
| `data/synthetic/mumbai_stations_v1/manifest.json` | Version, seed, reference date, source attribution, and SHA-256 file digests |
| `data/reference/mumbai_stations.json` | Sourced station anchors, canonical station IDs, aliases, and overlapping line memberships |
| `data/reference/STATION_SOURCES.md` | Geographic provenance, source license metadata, interchange handling, and limitations |
| `scripts/generate_synthetic_dataset.py` | Reproducible offline generator; no network/database access |
| `backend/clinic/management/commands/import_synthetic_dataset.py` | Database-free validation by default; explicit import into an empty dedicated synthetic database |

JSON is the import format because it preserves the current Django relationships. JSON Lines is the analytics format: one observation per line. Both can be read directly with Python's standard `json` library; a spreadsheet is not required.

### Dataset counts

| Entity | Count |
| --- | ---: |
| Patients / unique patient names / patient logins | 1,000 each |
| Synthetic doctors | 9 |
| Synthetic pharmacy accounts | 3 |
| Synthetic administrator | 1 |
| Medical consultations, including follow-ups | 2,208 |
| Allergy and chronic-condition entries | 758 |
| Lab observations | 1,321 |
| Placeholder prescriptions | 712 |
| Patient-reported adherence log rows | 3,384 |
| Analytics observations, including secondary conditions | 2,394 |
| Patients without simulated coordinates | 25 |

Primary disease labels are Dengue (188), Influenza (160), Asthma (86), Gastroenteritis (85), Hypertension (84), Type 2 diabetes (82), Anemia (69), Hypothyroidism (60), Malaria (42), and Osteoarthritis (36). Another 108 patients have a general consultation with no disease recorded. These primary categories sum to 1,000. Some patients have a second chronic condition, so counts across all disease observations are not mutually exclusive.

These numbers are generator choices, not estimates of population prevalence. “No disease recorded” does not mean confirmed healthy. Clinical measurements overlap between disease groups and include missing readings; labels are assigned by the simulation and cannot validate diagnostic rules.

## 2. Mumbai geography

| Membership within the requested three lines | Selected station areas |
| --- | --- |
| Central + Harbour | CSMT, Sandhurst Road, Kurla |
| Central + Western | Dadar |
| Western + Harbour | Mahim, Bandra, Andheri, Goregaon |
| Central | Byculla, Matunga, Sion, Ghatkopar, Vikhroli, Bhandup, Mulund, Thane, Dombivli, Kalyan |
| Western | Churchgate, Marine Lines, Mumbai Central, Lower Parel, Malad, Kandivali, Borivali |
| Harbour | Wadala Road, Sewri, Chembur, Govandi, Mankhurd, Vashi, Nerul, Belapur, Panvel |

The coordinate anchors were extracted from the [OpenCity suburban station resource attributed to BMC](https://data.opencity.in/dataset/mumbai-suburban-network-2025/resource/142fbd25-9ceb-41b2-900d-72479cdc179e). Its metadata identifies a KML resource, updated 25 November 2025, credited to OpenCity.in and labeled Public Domain. The reference file retains source feature IDs and the downloaded KML hash. Route memberships were separately checked against official railway references linked in `STATION_SOURCES.md`.

Each patient belongs to one station area. Interchanges have several memberships: the generated line-filter counts are Central 393, Western 349, and Harbour 534. Their sum exceeds 1,000 because the filters overlap. An “all lines” result must count a patient once.

Distinguish Mumbai municipality from the wider Mumbai Metropolitan Region: Thane, Kalyan-Dombivli, and Navi Mumbai are represented separately. These are selected stations, not an exhaustive network or a live timetable. Thane's Trans-Harbour connection is outside this classification. Dadar is not a Harbour station; Matunga is distinct from Matunga Road.

`station.latitude/longitude` are real public station anchors. `patient.geography.synthetic_latitude/synthetic_longitude` are generated nearby points. They are not homes, actual residence geocodes, travel histories, or infection locations. Jitter is a spatial simulation and is not checked against residential parcels, coastlines, or land use. Charts must say **synthetic station-area distribution**, never imply infection on a train.

## 3. How this matches the current project

Read the current implementation rather than relying on the original GitHub schema:

- `backend/accounts/models.py`: custom email-based `User`, generated compact `account_id`, password hashing, verification timestamps, and revocable sessions.
- `backend/clinic/models.py`: `Patient`, `MedicalRecord`, `ClinicalEntry`, `LabResult`, `Prescription`, `PrescriptionItem`, `MedicationAdherenceLog`, provider applications and audit events.
- `backend/clinic/serializers.py`: adult profile validation and supported vital keys.
- `backend/clinic/services.py`: currently approved doctors have direct patient access; pharmacy access is restricted. Legacy consent grants are not the current authorization path.
- `frontend/components/admin.tsx` and `admin-page.tsx`: current admin experience; keep its verification workflows intact.
- Current stack: Django 5.2/DRF/SimpleJWT, Neon PostgreSQL, Next.js 16, React 19, TypeScript and Tailwind/CSS modules. Inspect locked versions before adding dependencies.

The current schema has an address string but **no structured station/geographic fields**, and diagnosis is free text. The generated fixture preserves normalized disease keys and geography in sidecar fields. The current-schema importer imports supported clinical fields and saves source-to-database ID mappings; it does not silently cram geography into `vitals` or claim the admin ML dashboard already exists. Section 7 specifies the additional analytics schema and UI.

### Data dictionary

| Field/group | Meaning and mapping |
| --- | --- |
| `metadata` | Version, dataset ID, random seed, fixed reference date, synthetic provenance |
| `patients[].source_id` | Fixture join key such as `PAT0001`; never assumed to be the app's generated account/health ID |
| `user` | Fictional name, reserved-domain email, blank phone and simulated signup date; create with `User.objects.create_user()` |
| `profile` | DOB, gender, blood group including unknown, station-area address text, synthetic emergency-contact description, allergy status |
| `age_as_of` / `age_reference_date` | Derived age at 2026-09-29; compute age again from DOB for another date |
| `geography` | Canonical station ID, multiple line memberships, broad city, simulated point or explicit missing coordinates |
| `records[]` | Doctor source key, observation date, complaint, assigned disease label/key, notes and chart-compatible vitals |
| `vitals` | `systolic`, `diastolic`, optional `glucose_mg_dl`/`glucose_context`, temperature, pulse, weight and height; finite scalar values |
| `entries[]` | Sourced allergy or chronic-condition entry, author key, timestamp |
| `labs[]` | Simulated numerical result and unit, author and measurement timestamp; no invented clinical reference limits or files |
| `prescriptions[]` | Linked visit/doctor, issue/expiry dates, positive quantities and units; explicitly fake medicine items |
| `adherence[]` | Separate simulated patient-reported dose logs; missing dates mean unknown, not missed doses |
| `analytics.patient_key` | Pseudonymous join/deduplication key; not a numeric model feature |
| `analytics.episode_key` | Groups repeated follow-ups for the same simulated episode; do not count these as new cases |
| `analytics.observed_at` | Observation timestamp, not evidence of symptom onset or acquisition date |
| `evaluation_only_ground_truth` | Planted-group membership for simulation evaluation only, excluded from model inputs and ordinary admin API payloads |

Blood groups, demographic distributions, missingness, labels, and vital distributions are fictional. Contact numbers are blank because random valid-looking phone numbers could belong to real people. Credential/document IDs are conspicuously fake. There are no forged certificates, patient photos, actual drug regimens, or report files.

## 4. Generate or validate the dataset

Run from the repository root in PowerShell:

```powershell
# The requested dataset already exists. This validates it without database access:
node scripts/manage.mjs import_synthetic_dataset

# Create a NEW independent simulation; existing outputs/passwords are never replaced:
.venv/Scripts/python.exe scripts/generate_synthetic_dataset.py --dataset-id mumbai_stations_validation --seed 20261001 --as-of 2026-09-29
```

For a new dataset ID, pass its explicit dataset/credential/mapping paths to the importer. Generate evaluation scenarios with a different seed; do not regenerate seed 20260929 and call it independent validation. Public dataset content is reproducible for the same generator/reference/seed/date; test passwords are separately randomized with `secrets`.

All 1,013 credentials live in `.local/synthetic/mumbai_stations_v1/credentials.json`. Find the account by name, source ID or role. **Generating that file does not create accounts in your currently running app.** Import must succeed and the app must point to that same dedicated synthetic database before these logins work. Passwords use Django's normal hashing on import; plaintext stays in the local test-only login list. Do not reuse these passwords or upload the login list with analytics data.

## 5. Import into an isolated environment

The importer defaults to a dry run and refuses the normal application settings for `--apply`. It also refuses a target with existing users and never resets passwords or overwrites existing clinical data. Provider approvals in this fixture are synthetic test states, not real verification decisions.

Use a dedicated Neon development branch and an empty database named, for example, `synthetic_mumbai`. Do not copy real patient rows into this environment. The new settings require an explicit `SYNTHETIC_DATABASE_URL`, a `synthetic_` database-name prefix, and development mode. A branch's normal database name `neondb` alone does not satisfy that guard; create/select the dedicated database. Use its direct TLS endpoint for migrations/import.

Configure the connection string locally without placing its credentials in chat or this document, then run:

```powershell
$env:DJANGO_DEBUG = 'true'
# Set SYNTHETIC_DATABASE_URL locally to the dedicated database's connection string.
# It must be distinct from the database used by your normal application.

node scripts/manage.mjs migrate --settings=config.synthetic_settings
node scripts/manage.mjs import_synthetic_dataset --settings=config.synthetic_settings --apply
```

The output mapping is `.local/synthetic/mumbai_stations_v1/import-map.json`. It resolves fixture identities to database UUIDs, generated account IDs, and health IDs. Import is transactional and preserves historical clinic timestamps despite `auto_now_add`. Normal email delivery and automatic sessions are not used for seeding. Demo identities are explicitly preverified for isolated testing.

The mapping is exclusively created and flushed before the database transaction commits. Ordinary failures roll back rows and remove that newly created map, but filesystem and database commits are not one crash-atomic operation. After a power loss, inspect the target and mapping before retrying. An existing map or nonempty user table deliberately blocks replay.

For a local demo using the same synthetic target:

```powershell
$env:DJANGO_SETTINGS_MODULE = 'config.synthetic_settings'
npm run dev
```

Stop the dev process and remove `DJANGO_SETTINGS_MODULE` and `SYNTHETIC_DATABASE_URL` from that terminal when finished. Do not replace the application's saved main database URL to load this dataset. No data has been inserted into the configured Neon database as part of generating this package.

The seed can take several minutes because all 1,013 passwords receive individual Django hashes. Test-only fast hashers are confined to isolated automated tests; never change the application hasher to make a demo import faster.

## 6. ML topics and honest evaluations

### A. Disease distributions and cohorts

Start with counts by disease, station area, line and age band. Show distinct patients and denominator explicitly. Counts are observations in this dataset, not population incidence. Follow-up visits must not inflate the disease-case count. The `NO_RECORDED_DISEASE` category is an observation category, not proof of absence of disease.

### B. Geospatial DBSCAN for one disease in a chosen time window

Use scikit-learn DBSCAN with Haversine distance. Filter the disease and date window, select one latest eligible observation per patient/disease, exclude and report missing coordinates, then convert `[latitude, longitude]` from degrees to radians. Set `eps = radius_km / 6371.0088`, `metric='haversine'`, and `algorithm='ball_tree'`. See [DBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html) and [Haversine distance](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.haversine_distances.html).

Begin with **0.5 km / min_samples 5**, clearly labeled a demo setting. Examine a declared grid of radius `[0.3, 0.5, 0.8, 1.2]` km and minimum samples `[4, 5, 8, 12]`. `eps` is neighborhood reach, not the maximum radius of a cluster; chains can merge nearby station areas. Cluster `-1` means noise, not a patient health category.

For a visible demonstration use **2026-09-01 through 2026-09-29**, disease `DENGUE`. The generator deliberately places groups of 50 near Kurla, Andheri, and Vashi. `INFLUENZA` has groups of 35 near Ghatkopar, Borivali, and Nerul. Nearby background points may join a cluster; recovering every planted point perfectly is not guaranteed or required.

This default window is intentionally easy: 150 of the 151 eligible distinct dengue patients and 105 of the 111 eligible influenza patients are planted examples. Use it to demonstrate the workflow, then test a separate scenario with more recent background observations, overlapping groups, different densities and missing coordinates. Changing only the random seed is useful for repeatability checks but does not by itself establish robustness to different data-generating assumptions.

Railway line and station names are filters/display metadata. Do not feed ordinal-encoded station IDs, patient IDs, disease IDs, or planted labels into the coordinate clustering model. All persons in the selected disease cohort are already known to have a simulated recorded label; clustering is not diagnosis.

### C. Parameter sensitivity and cluster stability

Show eligible count, excluded count, number of non-noise clusters, cluster sizes, noise percentage, radius, minimum samples, time window, algorithm version, dataset hash and runtime for each run. Compare results under the declared parameter grid and repeated subsampling/coordinate perturbation; compare only shared patients and report coverage. This demonstrates sensitivity to assumptions instead of presenting one attractive map as definitive.

### D. Appropriate evaluation metrics

| Metric | Valid use | Conditions/limits |
| --- | --- | --- |
| Cluster count/size and noise proportion | Every DBSCAN run | Distinguish all-noise, one-cluster and multi-cluster results |
| Silhouette score with Haversine distance | Separation among non-noise groups | Exclude noise; require `2 <= number_of_clusters <= number_of_evaluated_samples - 1`; report coverage; otherwise return `null` with a reason |
| Adjusted Rand Index (ARI) | Agreement with planted groups or stability on common patients | Permutation-invariant; labels are arbitrary. The planted-group ARI only measures recovery of this generator's structure |
| Clustered-vs-noise precision/recall/F1 | Optional evaluation against the deliberately planted-vs-background flag | Binary event-detection comparison only; do not call it disease-prediction accuracy. Report the convention that all background points are evaluation negatives even if geographically dense |
| Runtime and memory | Operational comparison | Record sample size, environment and parameter set |

For planted-label comparisons, select matching patient keys and `primary_disease_code` for the filtered disease/time window and state how background and predicted noise are handled. A secondary chronic condition must not inherit the patient's dengue or influenza group label. Report ARI on planted patients as the primary synthetic recovery score and, if useful, an additional score including background under a disclosed convention. Do not tune parameters on the same hidden labels used for final reporting.

Silhouette validity and ARI interpretation follow the [scikit-learn silhouette documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html) and [ARI documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.adjusted_rand_score.html). Plain label equality, “99% disease accuracy,” and a diagnostic confusion matrix are not appropriate for geographic DBSCAN.

### Optional later experiments

K-means patient cohorts can be a separate exercise using standardized, clinically reviewed numeric features with explicit missingness and appropriate silhouette/Davies–Bouldin evaluation. Do not directly apply Euclidean K-means to raw latitude/longitude degrees or mix disease codes with measurements as ordinal numbers.

Weekly station/disease trend charts are descriptive. With only 1,000 fictional patients and roughly one year of observations, automatic outbreak forecasts or annual-seasonality claims would be unsupported. An anomaly-detection experiment would need a separate simulated event series, defined planted events, chronological holdout, and comparisons to a simple baseline. Keep these out of the first admin analytics increment.

## 7. Copy-ready implementation prompt

Use the following prompt with the project open. It is a build request for the **next implementation step**, not a claim that the ML UI already exists.

```text
Implement admin-only synthetic disease analytics in the existing MedyLink app.

CONTEXT AND BOUNDARIES
1. Inspect README.md, backend/accounts/models.py, backend/clinic/models.py,
   clinic/services.py, serializers.py, existing tests, and frontend/components/admin*.
   Follow frontend/AGENTS.md and the installed Next.js documentation before frontend edits.
2. Read docs/MUMBAI_DATASET_AND_ML_PROMPT.md, data/reference/STATION_SOURCES.md,
   and the dataset manifest. These are the current requirements. The earlier no-ML
   project specification is superseded for this admin analytics increment only.
3. Preserve current working email/password cookie authentication, CSRF, role checks,
   provider approval, direct-care permissions, patient cards and pharmacy workflows.
   Do not add MFA or consent-request flows from the old specification.
4. Retain Django/DRF/PostgreSQL and the existing Next.js/React/TypeScript UI.
   Add a compatible, pinned scikit-learn/NumPy analytics dependency set, and only the
   small chart/map dependencies required. Do not restore the original large ML stack,
   LLM calls, risk scoring, automated diagnosis, or treatment recommendations.

DATA AND REPRODUCIBILITY
5. Use the existing 1000-patient JSON fixture and credential-safe JSONL projection.
   Never use names, emails, phone numbers, passwords, DOB, street addresses, clinical
   free text or provider identities as clustering features. Patient keys may be used
   internally only for joins and deduplication.
6. Preserve six planted cluster labels in evaluation-only data; never pass them to fit().
   Keep a fixed seed/date and record manifest hash, library versions, parameters and
   evaluation coverage. Make a separately seeded synthetic validation scenario.
7. Leave existing real/unknown data outside the synthetic analytics cohort. Never infer
   that existing rows are real, synthetic, or approved solely from their display name.
   Do not send email or import fixtures into the normal configured database.

MINIMAL ANALYTICS SCHEMA
8. Add an analytics Django app or a similarly small isolated module. Use migrations for:
   a. DatasetBatch: key, synthetic flag, generator version, seed, as_of, manifest hash.
   b. StationArea: canonical station key, display name, aliases, coordinate anchor,
      line memberships, source feature IDs and provenance.
   c. PatientAreaObservation: dataset batch, patient FK, station FK, simulated coordinate
      pair or missing state, coordinate source and observation-valid date.
   d. DiseaseCode: stable local key and display label; no invented ICD certification.
   e. DiseaseObservation: batch, patient FK, disease FK, timestamp, episode key, source
      MedicalRecord or ClinicalEntry reference (exactly one source), unique import key.
   f. AnalyticsRun: batch, algorithm/version, filter/parameter JSON, status, counts,
      excluded reasons, metrics, runtime, aggregate cluster results and actor/time.
   Keep identifiers/foreign keys internal; admin results contain aggregates only.
9. Extend a dedicated synthetic analytics import command to join source IDs through
   the existing import-map.json. Preserve historical timestamps, structured station
   data, disease keys and episode IDs. Do not bury coordinates inside MedicalRecord.vitals.
   New analytical import must be idempotent by batch/source key, reject mismatching
   hashes, and never overwrite physician-authored records. Keep the original clinical
   fixture importer create-only and restricted to its empty synthetic target.
10. Future real-data capture needs explicit structured location and clinician-assigned
    disease coding. Do not guess them from address/diagnosis text or send patient text
    to external geocoding or AI services. First release processes synthetic batches only.

MODEL SERVICE
11. Implement a pure service that takes disease/date/line/station filters and DBSCAN
    radius/min_samples; validate enums, dates and reasonable bounds on the server.
12. Filter observations to the chosen batch/window. Deduplicate to one latest eligible
    observation per patient/disease; resolve ties deterministically. For incident-style
    summaries derive the first observed episode date from COMPLETE batch history before
    applying the date window, not the first follow-up that happens inside the window.
    Call ordinary counts 'patients with recorded observations'. Never call counts
    population incidence or infer symptom-onset dates from created_at.
13. Exclude missing coordinates and report how many were excluded. Convert latitude,
    longitude to radians in that order. DBSCAN must use Haversine distance and
    eps=radius_km/6371.0088; -1 is noise. Prevent duplicated interchange memberships
    from duplicating model rows. Test Dadar, Kurla, Bandra and CSMT specifically.
14. Include district/line/station filters as metadata filters; no ordinal station/disease
    codes, patient IDs or scenario labels in X. Do not fit a disease classifier.
15. Return sizes, station distribution and representative aggregate cluster centers,
    not raw patient points or patient identities. Use a suppression threshold of five
    distinct patients for displayed small-cell station/disease/age groups; apply it to
    exports and handle overlapping filters consistently. Synthetic-only scope must
    remain explicit; this threshold alone is not a guarantee of anonymization.

EVALUATION
16. Evaluate the declared radius/min_samples grid and report silhouette only when valid,
    with matching Haversine distance and non-noise coverage. Return null plus a reason
    for tiny samples, all-noise, one-cluster and otherwise undefined results; never zero
    as a stand-in for unavailable. Bound pairwise-distance memory use.
17. Calculate ARI against planted groups only in the evaluation path. Join labels by
    patient key AND matching primary disease after fitting; exclude unrelated secondary
    observations from planted-label evaluation. Disclose the background/noise convention, and
    label the result 'synthetic pattern recovery'. Optional binary precision/recall/F1
    refers to planted-vs-background grouping, not medical diagnosis.
18. Include stability over several seeded subsamples/coordinate perturbations on the
    shared patients, with retained-patient and noise coverage. Freeze chosen parameters
    before assessing a separately generated validation seed and harder background/
    overlap/density scenarios; disclose the deliberately easy default demo. DBSCAN is descriptive:
    do not claim conventional train/test prediction accuracy or real-world validation.

ADMIN API AND UI
19. Protect all analytics endpoints with the existing active, verified admin role check.
    Being a patient, approved doctor or approved pharmacy is insufficient. Keep existing
    admin clinical-record restrictions; analytics does not grant access to raw notes.
    Audit run/export actions without patient identities or credentials in payloads.
20. Suggested routes (adapt to existing conventions):
    GET /api/v1/admin/analytics/summary/
    GET /api/v1/admin/analytics/stations/
    POST /api/v1/admin/analytics/cluster-runs/
    GET /api/v1/admin/analytics/cluster-runs/<uuid>/
    POST /api/v1/admin/analytics/evaluation-runs/
    GET /api/v1/admin/analytics/evaluation-runs/<uuid>/
    State-changing routes require CSRF. Reuse computed runs by a canonical parameter/
    dataset-hash key, bound batch size/runtime, and avoid launching expensive fits per GET.
21. Add an admin Analytics section with a persistent 'Synthetic demonstration data'
    banner; disease, date, line and station filters; distinct patient counts; disease/
    age distributions; aggregate cluster map; cluster-size table; and evaluation table.
    Clearly show missingness, sample size, parameters, noise and unavailable metrics.
    Respect the existing dashboard navigation; keep provider-review pages usable.
    Read the map provider's terms, include required attribution, and never send patient
    data in external map-tile URLs. The map displays aggregate synthetic groups only.
22. Use patient counts, not visit counts, for headline disease distribution. Explain why
    line totals overlap at interchange stations. Show a single-patient count across all
    lines. Never label a group as a confirmed outbreak, contagion route or health risk.

TESTS AND DELIVERY
23. Test unauthenticated and all non-admin roles, direct URL/API access, CSRF, no PHI in
    results, dataset isolation, import hash/idempotency, date filtering, degrees/radians
    order, Haversine-km conversion, duplicate visits, interchange membership, coordinates
    missing/out of bounds, all-noise, one cluster, tiny samples and invalid parameters.
24. Test planted-group recovery with a declared parameter set and independent seed.
    Do not require a fabricated accuracy target. Verify record timestamps survived import,
    and compare cohort counts to SQL distinct-patient counts.
25. Run targeted backend tests, existing auth/clinical regression tests, frontend typecheck,
    lint and build, and one admin browser flow. Test schema changes on an isolated Neon
    branch/database. Report exactly which checks were run and which were unavailable.
26. Deliver migrations, the backend service/API, integrated admin UI, analytics import
    command, pinned dependencies, tests, methodology/run instructions and example
    aggregate results. Do not modify the main database or publish any live service as
    part of implementing the code. Remove dead placeholders and keep this increment small.
```

## 8. Dataset-regeneration prompt

```text
Generate an additional synthetic MedyLink dataset using the existing
scripts/generate_synthetic_dataset.py and data/reference/mumbai_stations.json.
Use a new dataset ID and seed, exactly 1000 unique fictional adult patients aged
18–85, one station area per patient across Central/Western/Harbour, and overlapping
line memberships for interchanges. Preserve the existing JSON import contract.
Keep station anchors sourced and simulated patient points separately labeled.
Use current model-compatible profiles, dated consultations, sourced allergy/condition
entries, optional labs, fake prescription workflow items and valid adherence logs.
Make realistic-looking variation, missingness and repeat visits, but never present
generator distributions or disease labels as clinical evidence. Generate unique
cryptographically random test passwords only under ignored .local/, using reserved
.test emails and no real contact numbers. Do not query or mutate the live database.
Keep pseudonymous analytics observations, planted evaluation labels and login details
in separate files. Validate every relationship, adult age at visit, date, quantity,
station membership and uniqueness constraint. Save counts, metadata and SHA-256 hashes.
Never overwrite an existing dataset, password list or source-to-database mapping.
```

The dataset supports development, software testing and demonstration of clustering/evaluation methods. It cannot establish disease prevalence, railway transmission, clinical accuracy, or the usefulness of a model for real patients.
