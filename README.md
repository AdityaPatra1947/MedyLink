# MedyLink

**Your health, connected.**

MedyLink connects patients, doctors and pharmacies around one health identity. Patients can follow their visits, reports and prescriptions; approved professionals can use a patient ID or QR card to continue care. Administrators review provider registrations and explore aggregate insights in a separate fictional-data demonstration.

Built with **Next.js, React, TypeScript, Django REST Framework and Neon PostgreSQL**, with a Python/scikit-learn module for an educational machine-learning project.

## Features

- **Public website:** responsive landing page, animated product previews, role-specific registration and accessible navigation with reduced-motion support.
- **Accounts:** email/password sign-in, password visibility controls, six-digit email verification, recovery, compact account IDs and security settings.
- **Patient portal:** a scrolling dashboard with a photo-enabled, reversible QR/PDF health card; visits, records, reports, prescriptions and dispensing history; blood-pressure/glucose trends and dose-log adherence.
- **Doctor portal:** QR/manual patient lookup, a saved patient list, shared clinical history, new consultations, report uploads and prescriptions. Earlier records retain their author and history; corrections are linked.
- **Pharmacy portal:** prescription lookup, allergy information and partial dispensing with shared remaining quantities across pharmacies.
- **Administration:** separate doctor/pharmacist approval queues, credential review, recorded decisions, security audit and aggregate analytics.
- **ML demonstration:** date/area filters, four-model comparison, automatic model selection, measurement grouping, geographic clustering and a retraining workflow.

Reports and card downloads use authenticated endpoints. Missing measurements stay unavailable. The synthetic environment adds labelled example health-score calculations and structured monthly reports; these are not clinically validated assessments.

## Roles and access

| Role | Main capabilities |
| --- | --- |
| Patient | View their own health information, manage their profile, download reports and track dose logs. |
| Doctor | After email verification and administrator approval, find a patient by complete ID/card and view or add clinical information. |
| Pharmacist | After verification and approval, access prescriptions and relevant allergies, then record dispensing. Full clinical history and reports are not available to this role. |
| Administrator | Review provider applications, inspect audit records and use aggregate analytics/ML. No public administrator signup. |

Provider access requires current approval and is recorded. The current care workflow does **not** require a separate patient permission request for each lookup. A health-card QR code is a locator, not an authentication credential.

## Technology

| Layer | Stack |
| --- | --- |
| Frontend | Next.js 16 App Router, React 19, TypeScript, CSS modules/global styles, Tailwind CSS 4 tooling, Lucide icons |
| API | Django 5.2, Django REST Framework, cookie-based JWT sessions, CSRF protection |
| Database | Neon PostgreSQL, Django models and migrations |
| Reports and uploads | ReportLab, pypdf, QR generation and private file storage |
| Analytics and ML | scikit-learn, NumPy, joblib; administrator-only Django routes |
| Validation | Django tests, Python unit tests, TypeScript, ESLint and Playwright |
| Deployment | Docker Compose, Gunicorn, Next.js standalone output, Redis and HTTPS proxy configuration |

## Quick start

You need **Node.js 22+**, **Python 3.12+**, Git and a Neon PostgreSQL database. Run commands from the cloned repository directory. A fresh checkout includes the fictional patient fixtures, but no working account passwords, database credentials, private uploads or trained model bundles. SMTP is optional for local development; no external ML API key or GPU is required.

```sh
git clone https://github.com/AdityaPatra1947/MedyLink.git
cd MedyLink
```

### 1. Install dependencies

On Windows, from PowerShell:

```powershell
npm ci
npm run setup
```

On macOS or Linux:

```sh
npm ci
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
node scripts/init-env.mjs
```

Setup creates `backend/.env` with new random development signing secrets and keeps any existing environment file. It does not create a database or import patient records.

To run only the 4,000-patient demonstration, continue with [Fresh 4,000-patient demo](#fresh-4000-patient-demo) after installing dependencies. The next three steps configure the regular application separately.

### 2. Configure the database

Create a Neon project or dedicated development branch, copy its PostgreSQL connection string, and set `DATABASE_URL` locally in `backend/.env`:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@YOUR-ENDPOINT-pooler.REGION.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

Replace the placeholders with your own connection details. The app supports pooled Neon connections and requires PostgreSQL; it does not silently fall back to SQLite. See [backend/.env.example](backend/.env.example) for other settings. Keep environment files private.

The frontend proxies `/api/v1/` to `http://127.0.0.1:8000` by default. For a different API address, create `frontend/.env.local` using [frontend/.env.example](frontend/.env.example). When changing ports, update the frontend origin and CSRF trusted origins together.

### 3. Migrate, create an administrator and run

```sh
npm run migrate
npm run admin
npm run dev
```

`npm run admin` asks for a name, email and password and creates a verified application administrator. Choose a password accepted by the configured validators. There is no shared default administrator password.

Open **[http://localhost:3000](http://localhost:3000)**. Signed-out visitors see the landing page; signed-in users see their dashboard. The launcher starts the frontend on **3000** and Django on **8000**. Press `Ctrl+C` to stop both. Check database readiness at `/api/v1/ready/`.

Register at `/register/patient`, `/register/doctor` or `/register/pharmacist`. Verify the email before signing in. Doctors and pharmacists must also submit credentials and receive administrator approval before using care features.

### 4. Configure email delivery

Local development uses Django's console email backend: verification codes and reset messages appear in the backend terminal. To send actual emails, configure `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and `DEFAULT_FROM_EMAIL` in `backend/.env`, using the example file as a reference. Restart the server afterward.

For Gmail, the interactive helper hides password input:

```powershell
.venv/Scripts/python.exe scripts/configure-smtp.py
```

On macOS/Linux, use `.venv/bin/python` instead. See [email setup](docs/GMAIL_SETUP.md) for SMTP configuration, delivery checks and verification-code behavior.

## Separate synthetic demonstration

The repository includes **all 4,000 fictional patient records across 34 Mumbai station areas** in two fixtures: the original 1,000-patient care-workflow fixture in `data/synthetic/mumbai_stations_v1/`, and 3,000 additional disease-training patients in `data/synthetic/mumbai_disease_v1/`. The expansion includes their simulated visits, measurements and labs. Public station references are real; people, nearby coordinates and clinical observations are simulated. Placeholder prescriptions are workflow examples, not treatment recommendations.

These files reproduce a generated baseline. They are not a snapshot of a running database: later consultations, uploaded reports, photos, manual edits, account changes and saved training runs require a private database/files backup or access to the existing database.

| Environment | Frontend | API | Accounts and data |
| --- | --- | --- | --- |
| Regular application | `http://localhost:3000` | Port `8000` | Your `backend/.env` database |
| Synthetic demonstration | `http://localhost:3001` | Port `8001` | A separate `synthetic_...` database configured in `.local/synthetic/.env` |

**Accounts are separate.** A login created or imported in one database does not automatically work in the other. Separate cookie names, signing keys, private storage and Next.js build directories allow both apps to run together. Demo emails are kept in memory rather than delivered.

### Fresh 4,000-patient demo

Complete dependency installation above, then create local passwords. On Windows:

```powershell
.venv/Scripts/python.exe scripts/init-synthetic-credentials.py
```

On macOS/Linux:

```sh
.venv/bin/python scripts/init-synthetic-credentials.py
```

The helper creates `.local/synthetic/mumbai_stations_v1/credentials.json` for the original **1,013 accounts**: 1,000 patients, nine doctors, three pharmacists and one administrator. It never replaces an existing file or changes database passwords. The extra 3,000 patients have **inactive accounts with unusable passwords**, for ML data only; they cannot sign in.

Create an **empty** Neon PostgreSQL database named `synthetic_mumbai` on a dedicated development branch. Create `.local/synthetic/.env` locally, replacing every placeholder:

```dotenv
SYNTHETIC_DATABASE_URL=postgresql://ROLE:PASSWORD@DIRECT_HOST/synthetic_mumbai?sslmode=require
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=REPLACE_WITH_A_NEW_LONG_RANDOM_SECRET
JWT_SIGNING_KEY=REPLACE_WITH_ANOTHER_LONG_RANDOM_SECRET
REDIS_URL=
FRONTEND_ORIGIN=http://localhost:3001
CSRF_TRUSTED_ORIGINS=http://localhost:3001,http://127.0.0.1:3001
```

Generate each signing secret independently by running this twice and pasting each result into the private file:

```sh
node -e "console.log(require('node:crypto').randomBytes(48).toString('hex'))"
```

The database name must start with `synthetic_`, and the URL must use TLS. Optionally add `SYNTHETIC_POOLED_DATABASE_URL` for the same database's pooled endpoint; web requests use it while management commands retain the direct endpoint. This environment never falls back to your regular application's database. Synthetic email is kept in memory, so SMTP is not required.

Run this complete import and training sequence from the repository root on either operating system:

```sh
# Validate published fixtures without connecting to a database.
node scripts/manage.mjs import_synthetic_dataset
node scripts/manage.mjs import_synthetic_expansion

# Import the original 1,000 patients and their analytics, then the other 3,000.
npm run synthetic:manage -- migrate --noinput
npm run synthetic:manage -- import_synthetic_dataset --apply
npm run synthetic:manage -- import_synthetic_analytics --apply
npm run synthetic:manage -- import_synthetic_expansion --apply

# Train the local models, then start the demonstration.
npm run synthetic:manage -- run_ml_training --task disease --sync
npm run dev:synthetic
```

On a clean database, this imports **4,000 patients, 11,195 consultations, 26,917 lab results and 12,719 disease observations**. The complete import, repeat expansion import, model training and admin insights response were verified against an isolated PostgreSQL database. Pulling the repository downloads the fixture files; it does not run these imports automatically.

The original clinical import refuses an existing user table or import mapping. Use this sequence for a fresh target; keep the generated `.local/synthetic/mumbai_stations_v1/import-map.json` with its matching database. For detailed validation and import behavior, see [the synthetic setup guide](docs/ADMIN_ANALYTICS.md#fresh-installation).

Sign in at **http://localhost:3001/login** using the `ADMIN001` account from your private credentials file. The admin workspace opens at `/admin/ml`, with geographic analysis and model comparison followed by doctor approvals, pharmacist approvals, audit, and security in one scrolling page. Sidebar links scroll to each section and update its URL; `/admin/analytics` is a legacy link that now opens ML insights. The optional [monthly-report demonstration](docs/PATIENT_REPORT_DEMO.md) has additional fixture prerequisites; normal migrations do not install it.

### Continue the existing demo on another device

After dependency installation, privately transfer the following files and keep the same synthetic database connection:

| Ignored path | What it preserves |
| --- | --- |
| `.local/synthetic/.env` | Existing dedicated database connection and environment settings |
| `.local/synthetic/mumbai_stations_v1/credentials.json` | Passwords matching the original imported accounts |
| `.local/synthetic/mumbai_stations_v1/import-map.json` | Original fixture-to-database mapping |
| `.local/synthetic/private-media/` | Existing uploaded PDFs, photos and other private files |
| `.local/ml/` (or custom `ML_ARTIFACT_ROOT`) | Saved model bundles and private evaluation artifacts |

The cloud database preserves records and saved-run metadata; a Git pull does not copy them. Do not generate replacement credentials or repeat the base import against that populated database. Start the existing environment with:

```sh
npm run synthetic:manage -- migrate --noinput
npm run dev:synthetic
```

If model files are unavailable, run `npm run synthetic:manage -- run_ml_training --task disease --sync` to recreate them. Model directories are scoped to the database endpoint/name and saved run; a different database should retrain. Existing report database rows do not recreate missing upload files, so preserve private storage. For a separate copy of all later edits, restore a private database backup together with its matching media and mappings.

Keep credentials, environment files, uploads, database backups and model bundles out of Git. Reinstall `.venv` and `node_modules` on the new device instead of copying them. The interactive map needs internet for OpenStreetMap tiles; no map API key is required.

## Machine learning

The admin workspace predicts the **primary disease** from measurements and symptoms recorded at a visit. This educational task does not provide a clinical diagnosis. Names, contact details and doctor identities are excluded from the feature matrix. Blood-pressure readings remain clinical measurements and disease-model inputs; predicting future blood pressure and its training have been removed.

Disease prediction compares **Logistic Regression, Decision Tree, Random Forest and KNN** using a stratified 80/20 patient split and five patient-level cross-validation folds. The best CV macro-F1 model can produce aggregate predictions only when final-test macro-F1 is at least 70% and accuracy is at least 75%. The page includes a searchable multi-disease filter, station-condition counts, accuracy bars, top-five feature contributions and independent retraining. [Run the disease task and synthetic generator](ml/DISEASE_TASK.md).

Disease classification and aggregate clustering use the following techniques:

| Technique | Purpose |
| --- | --- |
| Logistic Regression | A simple weighted classification baseline |
| Decision Tree | A sequence of learned measurement-based questions |
| Random Forest | An ensemble of randomized decision trees |
| KNN | Classification using the most similar training examples |
| K-Means | Aggregate groups with similar standardized measurements |
| DBSCAN | Geographic groups of synthetic recorded cases |
| PCA | Two-dimensional display of aggregate measurement-group centres |

The four classifiers share patient-separated train/test groups and five cross-validation folds. Preprocessing is fitted within training folds. The winner is selected by validation macro-F1; held-out accuracy, macro-F1, per-disease recall and confusion matrices are then reported. A fixed quality gate suppresses predictions when the selected model is not strong enough. The included disease evaluation selected Random Forest with **79.2% test accuracy** and **77.7% macro-F1**, passing the simulation gate. That saved run used the existing demonstration database; a fresh baseline import or later clinical edits can produce different coverage and scores. These results do not establish clinical accuracy.

The administrator can select all history or a date range and retrain with that data. Results are aggregate and small groups are suppressed. This release is restricted to explicitly synthetic datasets; it is not a validated anonymization system for real clinical deployment.

With the synthetic database configured and imported:

```sh
# Inspect eligible coverage without training.
npm run synthetic:manage -- run_ml_training --dry-run

# Train and save a new private run using all eligible history.
npm run synthetic:manage -- run_ml_training --task disease --sync
```

Disease is the default and only supported training task. Saved models stay under ignored `.local/ml/`. Read [the ML run guide and viva notes](docs/ML_INSIGHTS.md), [pipeline details](ml/README.md), [aggregate evaluation](ml/reports/disease_evaluation.json) and [the illustrated PDF guide](output/pdf/MedyLink_ML_Explained.pdf).

**Predictions support decisions and are not a diagnosis.** Synthetic evaluation results do not establish clinical accuracy, real outbreaks or treatment safety.

## Development commands

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the regular frontend and API |
| `npm run dev:synthetic` | Start the separately configured synthetic environment |
| `npm run migrate` | Apply normal database migrations |
| `npm run admin` | Create an administrator interactively |
| `npm run test:backend` | Run the isolated Django test suite |
| `npm run check` | Check frontend TypeScript and ESLint |
| `npm run build` | Build the production frontend |
| `npm --prefix frontend run test:e2e` | Run desktop/mobile Playwright tests against a running app |

Playwright is configured for Google Chrome; install Chrome before browser tests. The base URL defaults to port 3000 and can be overridden with `PLAYWRIGHT_BASE_URL`. Some workflow checks require prepared local fixtures; see [validation notes](docs/VALIDATION.md).

Run standalone ML tests on Windows with `.venv/Scripts/python.exe -B -m unittest ml.test_pipeline ml.test_disease_pipeline ml.test_train -v`, or use `.venv/bin/python` on macOS/Linux. Test the credential helper with the same Python executable and `-m unittest discover -s scripts -p test_init_synthetic_credentials.py -v`.

Backend tests use isolated in-memory SQLite by default, with database-specific checks skipped. For the isolated PostgreSQL suite, including concurrency checks:

```sh
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
```

Do not point test database settings at an application or production database.

## Docker and deployment

With `backend/.env` configured, Docker development still uses your Neon database:

```sh
docker compose build
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py bootstrap_admin
docker compose up
```

The development server commands above are not deployment commands. Production needs HTTPS, appropriate origins, secure cookies, Redis, SMTP, persistent private uploads and backup/restore procedures. See [operations](docs/OPERATIONS.md), `compose.production.yaml` and `deploy/`. Private records, reports, credentials, environment files and trained model bundles must never be published as static assets.

## Repository layout

```text
backend/
  accounts/          Authentication, sessions, account IDs and email
  clinic/            Profiles, providers, visits, reports and prescriptions
  analytics/         Synthetic imports, geographic analysis and ML APIs
  config/            Django settings, middleware and readiness checks
frontend/
  app/               Next.js routes and global styles
  components/        Landing page, role dashboards and shared controls
  lib/               Typed API client and shared types
  tests/             Playwright browser tests
ml/                  Training pipeline, unit tests and aggregate evaluation
data/                Public reference data and synthetic fixtures
scripts/             Setup, local launchers and fixture tooling
docs/                Product, API, setup and evaluation documentation
deploy/              Reverse-proxy configuration
```

Additional documentation: [clinical API](backend/clinic/API.md), [analytics API](docs/ANALYTICS_API_CONTRACT.md), [patient health data](docs/PATIENT_HEALTH_DATA.md), [doctor workflow](docs/DOCTOR_DASHBOARD.md), [dashboard navigation](docs/DASHBOARD_NAVIGATION.md) and [implementation decisions](docs/IMPLEMENTATION.md). The API schema is available at `/api/v1/schema/` when the server is running.
