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

You need **Node.js 22+**, **Python 3.12+**, Git and a Neon PostgreSQL database. Run commands from the cloned repository directory. A fresh checkout contains no working account passwords, database credentials or SMTP secrets.

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

The demonstration contains **1,000 fictional adult patients across 34 Mumbai station areas**, generated clinical observations and fictional professionals. Public station references are real; people, nearby coordinates and clinical observations are simulated. Placeholder prescriptions are workflow examples, not treatment recommendations.

| Environment | Frontend | API | Accounts and data |
| --- | --- | --- | --- |
| Regular application | `http://localhost:3000` | Port `8000` | Your `backend/.env` database |
| Synthetic demonstration | `http://localhost:3001` | Port `8001` | A separate `synthetic_...` database configured in `.local/synthetic/.env` |

**Accounts are separate.** A login created or imported in one database does not automatically work in the other. Separate cookie names, signing keys, private storage and Next.js build directories allow both apps to run together. Demo emails are kept in memory rather than delivered.

First generate your own private account credentials for the published fixture:

```powershell
.venv/Scripts/python.exe scripts/init-synthetic-credentials.py
```

Use `.venv/bin/python` on macOS/Linux. The helper writes fresh random passwords under ignored `.local/synthetic/mumbai_stations_v1/credentials.json`, never overwrites an existing file and never changes a database. Keep this file with the database into which you import those accounts.

Follow [the synthetic setup guide](docs/ADMIN_ANALYTICS.md#fresh-installation) to create an empty dedicated Neon database, configure `.local/synthetic/.env`, and import the clinical and analytics fixtures. Synthetic imports must not target your normal application database. After setup:

```sh
npm run dev:synthetic
```

Sign in on port **3001** using the locally generated demo administrator credentials. Open `/admin/analytics` for geographic analysis or `/admin/ml` for model comparison. The optional [monthly-report demonstration](docs/PATIENT_REPORT_DEMO.md) has additional fixture prerequisites; normal migrations do not install it.

## Machine learning

The admin workspace has two educational prediction tasks: **primary disease classification** from measurements and symptoms at a visit, and **next-visit blood pressure** from eligible earlier observations. Neither provides a clinical diagnosis. Names, contact details and doctor identities are excluded from both feature matrices.

Disease prediction compares **Logistic Regression, Decision Tree, Random Forest and KNN** using a stratified 80/20 patient split and five patient-level cross-validation folds. The best CV macro-F1 model can produce aggregate predictions only when final-test macro-F1 is at least 70% and accuracy is at least 75%. The page includes a searchable multi-disease filter, station-condition counts, accuracy bars, top-five feature contributions and independent retraining. [Run the disease task and synthetic generator](ml/DISEASE_TASK.md).

The existing blood-pressure task and aggregate clustering use the following techniques:

| Technique | Purpose |
| --- | --- |
| Logistic Regression | A simple weighted classification baseline |
| Decision Tree | A sequence of learned measurement-based questions |
| Random Forest | An ensemble of randomized decision trees |
| Gradient Boosting | Sequential trees that improve on earlier errors |
| K-Means | Aggregate groups with similar standardized measurements |
| DBSCAN | Geographic groups of synthetic recorded cases |
| PCA | Two-dimensional display of aggregate measurement-group centres |

The four classifiers share patient-separated train/test groups and cross-validation folds. Preprocessing is fitted within training folds. The winner is selected by validation macro-F1; held-out accuracy, precision, recall, F1 and confusion matrices are then reported alongside two simple baselines. A fixed quality gate suppresses predictions when the selected model is not strong enough. The included evaluation did **not** pass that gate; the comparison and grouping remain available.

The administrator can select all history or a date range and retrain with that data. Results are aggregate and small groups are suppressed. This release is restricted to explicitly synthetic datasets; it is not a validated anonymization system for real clinical deployment.

With the synthetic database configured and imported:

```sh
# Inspect eligible coverage without training.
npm run synthetic:manage -- run_ml_training --dry-run

# Train and save a new private run using all eligible history.
npm run synthetic:manage -- run_ml_training --sync

# Append 3,000 seeded patients once, then train the separate disease task.
npm run synthetic:manage -- generate_synthetic_data --count 3000 --seed 42
npm run synthetic:manage -- run_ml_training --task disease --sync
```

Saved models stay under ignored `.local/ml/`. Read [the ML run guide and viva notes](docs/ML_INSIGHTS.md), [pipeline details](ml/README.md), [aggregate evaluation](ml/reports/evaluation.json) and [the illustrated PDF guide](output/pdf/MedyLink_ML_Explained.pdf).

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

Run standalone ML tests on Windows with `.venv/Scripts/python.exe -B -m unittest ml.test_pipeline -v`, or use `.venv/bin/python` on macOS/Linux. Test the credential helper with the same Python executable and `-m unittest discover -s scripts -p test_init_synthetic_credentials.py -v`.

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
