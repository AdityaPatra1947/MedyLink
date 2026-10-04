# Admin analytics: synthetic Mumbai demonstration

MedyLink's administrator-only analytics use deliberately fictional data. The published fixtures contain **4,000 patients**: the unchanged original 1,000-patient care-workflow dataset and a 3,000-patient disease-training expansion. They provide date/disease/location filters, aggregate charts, geographic DBSCAN groups and repeatable evaluations. The companion [ML insights page](ML_INSIGHTS.md) adds a four-model comparison, K-Means and PCA.

## Fresh installation

Complete the dependency installation in the [root README](../README.md#1-install-dependencies) first: Git, Node.js 22+, Python 3.12+, root/frontend npm dependencies and the backend Python requirements. On Windows run `npm ci` then `npm run setup`. macOS/Linux commands are in the same README section. These steps create an isolated demonstration; they do not seed the regular application database.

External requirements are a dedicated Neon PostgreSQL database connection and locally generated signing secrets. No external ML service, ML API key or GPU is required. SMTP is unnecessary for the synthetic environment, which does not deliver email. Internet access is needed for the database, dependency installation and OpenStreetMap background tiles; the map requires no API key.

### 1. Generate private credentials

From the repository root, on Windows:

```powershell
.venv/Scripts/python.exe scripts/init-synthetic-credentials.py
```

On macOS/Linux:

```sh
.venv/bin/python scripts/init-synthetic-credentials.py
```

The helper verifies the original fixture against its manifest and writes unique random passwords for its **1,013 accounts** to `.local/synthetic/mumbai_stations_v1/credentials.json`: 1,000 patients, nine doctors, three pharmacists and one administrator. It never connects to a database, prints passwords, or replaces an existing credentials file. The extra 3,000 disease-training patients have inactive accounts with unusable passwords; they cannot sign in. No working passwords are included in the public repository.

The accounts in this private file become usable only after import. Preserve the file with its matching imported database. Generating different credentials later would not change passwords already in a database.

### 2. Configure a separate Neon database

Create an empty PostgreSQL database whose name starts with `synthetic_`, preferably on a dedicated Neon development branch. Create `.local/synthetic/.env` with your own values:

```dotenv
SYNTHETIC_DATABASE_URL=postgresql://ROLE:PASSWORD@DIRECT_HOST/synthetic_mumbai?sslmode=require
SYNTHETIC_POOLED_DATABASE_URL=postgresql://ROLE:PASSWORD@POOLED_HOST/synthetic_mumbai?sslmode=require
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=GENERATE_A_NEW_LONG_RANDOM_SECRET
JWT_SIGNING_KEY=GENERATE_ANOTHER_LONG_RANDOM_SECRET
REDIS_URL=
FRONTEND_ORIGIN=http://localhost:3001
CSRF_TRUSTED_ORIGINS=http://localhost:3001,http://127.0.0.1:3001
```

The pooled URL is optional; the launcher uses it for web requests and keeps the direct URL for management commands. Generate each signing secret independently, for example by running this command twice and pasting each result into the private environment file:

```sh
node -e "console.log(require('node:crypto').randomBytes(48).toString('hex'))"
```

Synthetic settings reject an absent connection URL or a database name without the `synthetic_` prefix. They require TLS and explicitly select `config.synthetic_settings`; the regular `backend/.env` connection is never a fallback. Never use an application or production database for a synthetic import.

### 3. Validate, import all 4,000 patients and train

```sh
# Read-only fixture validation; no database connection.
node scripts/manage.mjs import_synthetic_dataset
node scripts/manage.mjs import_synthetic_expansion

# Apply migrations and import application entities into the empty target.
npm run synthetic:manage -- migrate --noinput
npm run synthetic:manage -- import_synthetic_dataset --apply

# Validate the analytics sidecar, then persist its structured observations.
npm run synthetic:manage -- import_synthetic_analytics
npm run synthetic:manage -- import_synthetic_analytics --apply

# Import the published 3,000-patient expansion after the original analytics.
npm run synthetic:manage -- import_synthetic_expansion --apply

# Fit and save disease models privately for this database.
npm run synthetic:manage -- run_ml_training --task disease --sync
npm run dev:synthetic
```

The clinical importer refuses a nonempty user table or an existing import mapping. It never overwrites accounts. Its private mapping is `.local/synthetic/mumbai_stations_v1/import-map.json`; keep it with the database and fixture version. Do not repeat the clinical import on an already populated demonstration. The analytics import has separate checksum and idempotency checks.

The expansion reads `data/synthetic/mumbai_disease_v1/patients.jsonl`, `visits.jsonl` and `manifest.json`. Without `--apply`, it validates the published files without database access. Applying requires the imported original clinical and analytics dataset in the dedicated synthetic database. Reapplying the same expansion is a no-op; it does not reset original accounts or clinical records. Successful import adds 3,000 patients with 8,987 visits, bringing the mapped population to 4,000. Training writes its model files locally; the aggregate evaluation committed to Git is not itself a usable model.

### 4. Sign in

Open **http://localhost:3001/login**. Read the account with source ID `ADMIN001` in your private credentials file and sign in with its generated email and password. Patient, doctor and pharmacist credentials are in the same file. Passwords are hashed when imported into PostgreSQL.

Open **http://localhost:3001/admin/ml** for the administrator workspace, including geographic analysis and disease-model comparison. `/admin/analytics` is a legacy link to this workspace. Fresh fixture accounts are separate from manually registered users on port 3000. Accounts and later local edits are never copied between databases by the launcher.

## Continue an existing demonstration on another device

A Git pull supplies code and generated fixtures, not your running database, uploaded files or fitted models. To continue the same demonstration, install dependencies on the new device, retain access to the same synthetic database and transfer these ignored files privately:

| Path | Purpose |
| --- | --- |
| `.local/synthetic/.env` | Dedicated connection and environment settings |
| `.local/synthetic/mumbai_stations_v1/credentials.json` | Existing imported logins |
| `.local/synthetic/mumbai_stations_v1/import-map.json` | Original source-to-database mapping |
| `.local/synthetic/private-media/` | Uploaded reports, photos and other private file bytes |
| `.local/ml/` | Database-scoped model bundles and evaluations, unless a custom `ML_ARTIFACT_ROOT` is used |

Keep a custom model directory instead if `ML_ARTIFACT_ROOT` was configured. Never publish these files or database backups in Git. Install a new `.venv` and `node_modules` for the destination device; build output is disposable.

Do not generate replacement credentials or repeat the original clinical import. Apply migrations and start:

```sh
npm run synthetic:manage -- migrate --noinput
npm run dev:synthetic
```

If the existing demo has only the original 1,000 patients, validate and apply `import_synthetic_expansion` once, then train. If a saved model bundle is missing, retrain with `npm run synthetic:manage -- run_ml_training --task disease --sync`. Model paths depend on the database endpoint/name and run ID; a new database should retrain rather than assume old files match.

The published files reproduce the generated baseline, not later local edits. To preserve those in a separate database, restore a private database backup together with its matching media and mappings. Report rows store private file references: rerunning report enrichment skips already-existing rows and does not restore missing PDF bytes. Copy private media when keeping the existing report history.

## Running both environments

`npm run dev` uses the regular application on ports 3000/8000. `npm run dev:synthetic` uses the separate demonstration on 3001/8001. Independent signing keys, cookie names, private upload storage and `.next-synthetic` build output isolate the demonstration. Outgoing demo email uses Django's in-memory backend and is not delivered.

Set `SYNTHETIC_FRONTEND_PORT` and `SYNTHETIC_API_PORT` in the private synthetic environment file to change its ports. Open the configured URL directly when using custom ports. `Ctrl+C` stops both services started by that launcher.

## Data and dashboard

The original `mumbai_stations_v1` fixture contains 1,000 adult patients, 9 doctors, 3 pharmacy accounts, one administrator, 2,208 medical records, 758 allergy/condition entries, 1,321 labs, 712 placeholder prescriptions, 3,384 adherence logs and 2,394 structured analytics observations. Geography covers 34 selected Central, Western and Harbour station areas, including interchange memberships. Twenty-five original patients deliberately lack synthetic coordinates.

The published `mumbai_disease_v1` expansion adds 3,000 patients and 8,987 visits with disease labels, symptoms, measurements and labs, reusing the original station areas and approved doctors. Together they provide the 4,000-patient baseline. See [the expansion manifest and file guide](../data/synthetic/mumbai_disease_v1/README.md) for its schema and verified counts. Later consultations, report enrichment and manual edits can change application and training counts; they are not embedded in the public fixtures.

The administrator can filter by disease, date range, railway line and station area; inspect counts and distributions; run DBSCAN; and compare evaluations. The interactive Leaflet/OpenStreetMap map plots public station anchors and aggregate synthetic group centres, never patient homes. Lists remain usable if background tiles cannot load.

The original fixture's planted example uses **Dengue**, **1-29 September 2026**, all lines/stations, a **0.5 km** neighbourhood radius and **5** minimum samples, with groups near **Kurla, Andheri and Vashi**. Influenza has planted groups near **Ghatkopar, Borivali and Nerul**. The expansion and later clinical rows can change current counts and group shapes. Other diseases or narrower filters can correctly produce no groups. These dates illustrate the original fixture, not a limitation on supported filters.

Counts represent patients with recorded observations in the dataset, not population prevalence or incidence. Follow-up visits are deduplicated to the latest observation per patient and disease in the selected window. First-recorded episode dates use the full dataset history before filtering. Line memberships and disease categories overlap, so their totals must not be added together.

## Rebuild the expansion files

Normal setup imports the committed JSONL files. Developers can reproduce the expansion offline, without a database connection, with:

```powershell
.venv/Scripts/python.exe scripts/build_synthetic_expansion.py
```

On macOS/Linux, use `.venv/bin/python`. This fixed seed-42 build publishes synthetic data only, never passwords, uploads or model bundles. The separate `generate_synthetic_data --count 3000 --seed 42` management command generates the same seeded population in a configured demo and is an alternative developer workflow, not an additional population required after the published expansion import.

## Geographic clustering and evaluation

- **DBSCAN:** coordinates are converted to radians and the neighbourhood radius is divided by Earth radius for haversine distance. Date is a filter, not a spatial coordinate. Missing locations are excluded and counted.
- **Noise and coverage:** describe how many eligible coordinate-bearing observations belong to density groups. Noise is not a health-risk or severity label.
- **Silhouette:** measures separation among non-noise groups using geographic distance. It is unavailable when fewer than two usable groups exist; the API explains missing metrics instead of inventing a score.
- **Parameter comparison:** evaluates four radii (0.3, 0.5, 0.8 and 1.2 km) and four minimum-sample values (4, 5, 8 and 12). The highest value is not automatically a medically correct choice.
- **Stability:** seeded 80% subsamples and 30-metre perturbations are compared with adjusted Rand index (ARI).
- **Synthetic pattern recovery:** evaluation-only planted labels are compared after fitting. They are never model inputs. Patients are matched to truth for the selected primary disease; background and model noise each form a reference/predicted group.

The original planted scenario is intentionally easy. High ARI indicates recovery of an invented pattern, not diagnostic accuracy or evidence of an outbreak. Independent simulations and appropriately governed real datasets would be needed for a broader study. Classifiers, K-Means and PCA are described separately in [ML insights](ML_INSIGHTS.md).

## Storage, privacy and access

The analytics app stores dataset provenance, station references, cohort links, structured observations, separate evaluation truth and aggregate results. Repeated identical run inputs reuse saved results; filters, parameters and software versions accompany each run.

Every analytics endpoint requires an active verified administrator. Patients, doctors and pharmacists cannot access these routes. POST requests retain cookie authentication and CSRF protection. Responses do not contain patient names, login details, clinical text, individual coordinates or hidden evaluation labels.

Small displayed patient counts of one to four and small-group geometry are suppressed. This safeguard does not formally prevent inference from repeated overlapping aggregate queries. This release remains synthetic-only. See the [analytics API contract](ANALYTICS_API_CONTRACT.md) for response shapes, parameter bounds and unavailable-metric explanations.

## Validation

```sh
npm run test:backend
npm run check
npm run build
```

Backend tests default to isolated in-memory SQLite; never set `TEST_DATABASE_URL` to an application database. Use the root README's isolated PostgreSQL test container for database-specific concurrency checks.

After preparing and starting the synthetic environment, optional API/browser workflows read the ignored local credentials file:

```sh
node scripts/verify_synthetic_api.mjs
node scripts/verify_synthetic_ui.mjs
```

Set `SYNTHETIC_VERIFY_URL` for a custom local port. These scripts exercise demo login, filters, saved runs, invalid/empty input, CSRF protection, role denial and responsive screens. Reports and screenshots are written under ignored `.local/synthetic/`.
