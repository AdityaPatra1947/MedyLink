# Synthetic Mumbai station-area patient dataset

**1,000 fictional patients · 34 station areas · ages 18–85 · reference date 2026-09-29**

Use [the complete guide and implementation prompt](../../../docs/MUMBAI_DATASET_AND_ML_PROMPT.md) for field definitions, geographic provenance, safe import, and admin clustering/evaluation requirements.

- `dataset.json`: related application fixtures; 1,000 patients plus 9 doctors, 3 pharmacies and 1 administrator.
- `analytics_observations.jsonl`: pseudonymous dated observations; deduplicate patient/disease rows before clustering.
- `evaluation_only_ground_truth.json`: intentionally planted group labels; exclude from model inputs.
- `validation_report.json`: counts and data checks.
- `manifest.json`: reproducibility metadata, provenance, and generated-data file digests.

The separate local login list is `.local/synthetic/mumbai_stations_v1/credentials.json` at the repository root. Create your own credentials on a fresh checkout with `python scripts/init-synthetic-credentials.py`. The helper generates random demo passwords and refuses to replace an existing credential file. The file is excluded from Git and does not belong in an analytics export. These accounts do not exist in your running app until the dedicated import succeeds.

After generating local credentials, run `node scripts/manage.mjs import_synthetic_dataset` from the repository root to validate the fixture without database access. Importer tests cover cookie login, password hashing, timestamp preservation, protected targets, and rollback. To create the accounts and records in a separate PostgreSQL database, follow the [synthetic setup guide](../../../docs/ADMIN_ANALYTICS.md).

Station anchors are sourced; all people, health observations, nearby patient points, and professional identities are generated. Contacts use reserved `.test` email addresses and blank telephone numbers. Prescriptions use fake workflow items, not real treatment regimens. No credential or medical-report files are fabricated. Use this data for development and simulation evaluation, not clinical conclusions or real disease surveillance.
