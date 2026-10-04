# Implementation decisions and validation

The user's request was to keep the project simple and use Neon PostgreSQL. The reference Markdown supplies the product requirements; its embedded build prompt is treated as project context.

## Deliberate simplifications

- Two Django apps (`accounts` and `clinic`) instead of a separate app for every medical entity. Authorization and clinical transactions remain in Django.
- One responsive Next.js app with reusable role portals. The browser uses a small typed `fetch` wrapper and React state instead of adding Axios, Zustand, React Query and a second form framework. Identity is loaded from the API and sensitive state is not persisted in browser storage.
- A single provider application captures professional and, for pharmacists, shop identity. Submission versions and recorded decisions preserve review history. One named pharmacist represents one shop.
- Allergies and conditions share one sourced-entry table. Entries can be resolved with a reason, preserving history.
- Clinical notes are finalized at creation. Corrections are new linked entries; there is no generic edit/delete endpoint for doctor-authored records.
- No Redis service is required for a single-process local trial. Production refuses missing Redis configuration and uses shared counters.
- No billing, stock management, appointment system, AI/CDSS, reminder service, mobile app or analytics dashboard.
- Evidence validation is an explicit manual review after private quarantine and signature/size checks. Automatic antivirus integration is not included; deployment operators must scan evidence before recording validation. This limitation is visible in the runbook.
- The health ID is local to this application. It is not ABHA, Aadhaar or another government identifier.

## Current care workflow

- All roles use email and password after email-code verification. Authenticator setup, secrets, recovery codes and endpoints were removed.
- Approved doctors can find patients by exact account ID, health ID or card and access clinical information directly. Approved pharmacies can find prescriptions, with no patient permission request. Role restrictions, professional suspension and activity logging remain. Historical grant rows are retained solely as history.
- The patient dashboard includes a photo card that flips to its QR/emergency-contact back, and recent visits containing explicitly linked prescriptions/reports. Older standalone prescriptions remain in the full prescription history; all reports remain in the report library.
- Uploaded report storage follows the existing private file volume. No public media directory or external storage provider is added.

## Verification boundaries

Fast Django tests use an isolated SQLite database only as a test fixture; the actual application requires PostgreSQL. PostgreSQL-only concurrency tests run with `compose.test.yaml` or a dedicated `TEST_DATABASE_URL`, and must pass before using the dispensing workflow in production. Tests may create/drop a `test_...` database: never reuse production test credentials.

Real Neon connectivity requires the user's local connection string. Real email delivery requires their SMTP service. Backup restoration requires an isolated database and evidence storage. These external outcomes must not be inferred from a successful build or a fast unit/integration test run.

See `VALIDATION.md` for the checks actually executed on this checkout and remaining environment-dependent checks.

## Version references

The baseline uses [Django 5.2 LTS](https://www.djangoproject.com/download/) and [Next.js 16](https://nextjs.org/docs/app/getting-started/installation), with resolved versions in the lockfiles. Neon configuration follows its [Django guide](https://neon.com/docs/guides/django). Review supported versions and security advisories with future dependency updates.
