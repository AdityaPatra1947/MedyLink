# Operations

## Deployment

Use a controlled host with Docker, HTTPS certificates and a Neon PostgreSQL database. One canonical origin serves Next.js at `/` and Django at `/api/v1/`. Do not expose the backend, Redis or credential-file volume directly to the internet.

1. Set production values in a secrets manager or a protected `backend/.env`: `DJANGO_DEBUG=false`, distinct long random Django/JWT signing secrets, Neon `DATABASE_URL`, explicit `DJANGO_ALLOWED_HOSTS`, HTTPS `FRONTEND_ORIGIN` and matching `CSRF_TRUSTED_ORIGINS`.
2. Set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, SMTP host/port/user/password, TLS and a real `DEFAULT_FROM_EMAIL`. Confirm verification and reset delivery with the chosen mail service. Development console delivery is rejected in production.
3. Place managed TLS certificates in `deploy/tls/fullchain.pem` and `deploy/tls/privkey.pem`. Restrict filesystem permissions and automate certificate renewal outside the application. Set your actual hostname in `deploy/nginx.conf`.
4. Use `docker compose -f compose.production.yaml build`. The production configuration supplies Redis and the private file path. Run `docker compose -f compose.production.yaml run --rm backend python manage.py check --deploy --fail-level WARNING`.
5. Back up the existing database and evidence volume before an upgrade. Run `docker compose -f compose.production.yaml run --rm backend python manage.py migrate --noinput` exactly once per release, then start `docker compose -f compose.production.yaml up -d`.
6. Bootstrap the first admin with the interactive management command and exercise the complete patient/doctor/pharmacy flow with synthetic records.

Do not enable Django Admin for clinical models. The administrator portal reviews provider/security metadata; it is not a blanket medical-record viewer. HTTP-only JWT cookies are host-only, secure in production, and guarded by CSRF on all mutations. The frontend never stores bearer tokens in local storage.

The reverse proxy overwrites forwarded IP/protocol headers. Only it may reach the backend. Rate limiting uses shared Redis in production; Redis failure denies requests rather than silently allowing unlimited attempts. TLS termination at a different managed proxy must preserve the same trust boundary and headers.

## Private uploaded files

Uploads are private, size/type checked, and assigned server-generated names. Patient photos accept JPEG/PNG up to 2 MiB; medical reports accept PDF/JPEG/PNG up to 10 MiB. The owner and currently approved doctors may read reports; pharmacies and administrators cannot. Credential evidence stays quarantined until the administrator records its validation result. Review documents in a hardened isolated viewer and scan them with the organization's malware scanner before recording a safe result. Manual evidence validation is an operator assertion, not an integrated antivirus scan. Review validity and professional identity independently before approval.

Back up the private volume along with the database. Encrypt the underlying disk and backup destination and restrict access to the application/backup identities. Do not configure a public `/media/` route or CDN for these files.

The MedyLink Compose project deliberately keeps the existing Docker evidence volume named `arogyatrack-lite_evidence`, so the rename does not disconnect uploaded files. A new installation can set `MEDYLINK_EVIDENCE_VOLUME=medylink_evidence` in the Compose environment. On an existing installation, migrate and verify the uploaded files before switching this value.

If the old Compose deployment is running, stop its containers with
`docker compose -p arogyatrack-lite -f compose.production.yaml down` before starting
the MedyLink deployment. Do not add `-v`; uploaded evidence must stay in its volume.
This prevents the old and new project names from trying to bind the same ports.

## Backups and restoration

Define recovery targets before handling real data. A starting operating target to evaluate is a maximum 24-hour data-loss window and a four-hour recovery time; these are proposals, not achieved service guarantees.

- Configure the Neon plan's restore/history retention and an independent encrypted logical backup schedule appropriate to those targets. Verify the actual retention in the Neon console.
- For logical backups, use a PostgreSQL client version compatible with the server, a direct connection and a protected `PGSERVICEFILE`/`PGPASSFILE` (permissions restricted). Avoid placing database passwords on command lines or in logs.
- Example using a configured `medylink_backup` libpq service: `pg_dump --dbname=service=medylink_backup --format=custom --file=backup.dump`. Upload the dump to your encrypted restricted backup destination, and record checksum, schema version, time and outcome.
- Back up private credential, report and patient-photo files and retain Django/JWT signing keys separately in the secrets manager.
- Restore into an **isolated, empty** database/Neon branch with separate credentials, never over a live database. Use `pg_restore --dbname=service=medylink_restore --no-owner --no-acl backup.dump`, restore the matching evidence files, run migrations, and point an isolated app deployment at it.
- Disable real outgoing email in the isolated development restore. Check account counts, provider evidence, record attribution, patient-photo/report authorization, prescription balances and PDF downloads. Confirm suspended or expired providers cannot access clinical information. Record restore duration and integrity results.
- Run this drill before launch and after significant storage/schema changes. A written procedure alone does not establish tested recoverability.

## Rollback and credential rotation

Keep prior application images and migration history. Prefer compatible forward fixes. Do not reverse destructive migrations or restore a pre-release backup over new production writes without an explicit data-recovery plan. Stop writes when a rollback requires database restoration.

Database password rotation: issue a new least-privilege credential, update the secrets manager, restart workers and verify readiness, then revoke the old credential. JWT signing-key rotation invalidates existing login cookies; require users to sign in again. Django secret rotation affects Django signing mechanisms.

## Provider suspension and account security

Use the administrator portal to suspend a provider with a recorded reason. The API checks current professional approval on each protected request, including downloads and dispensing retries. Patient grants are no longer part of authorization. Reapproval restores access according to the professional role.

All roles can revoke individual login sessions or sign out on all devices. Password reset revokes sessions. Sign-in uses verified email and password; there is no authenticator enrollment, recovery-code flow, or authenticator reset command.

## Monitoring and incident handling

Monitor liveness `/api/v1/health/`, readiness `/api/v1/ready/`, API error rates, SMTP failures, database/Redis health, private-storage capacity and backup job failures. Keep token-bearing query strings, cookies, raw QR locators, request bodies and clinical notes out of request logs and error trackers. Audit events contain actor/resource references and outcomes, not clinical payloads.

On suspected unauthorized access: preserve the audit trail, disable the affected account/sessions, suspend implicated providers, rotate exposed secrets, investigate lookup/download history, and follow the operator's incident and notification procedures. Previously downloaded or printed records cannot be remotely recalled.

Retention, deletion requests, support contacts and applicable healthcare/privacy policies must be established by the operator. This code and runbook do not certify regulatory compliance.
