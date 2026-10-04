# Validation record

Latest checks completed on 29 September 2026 for the patient and doctor dashboard, authenticator removal and compact account ID updates.

| Check | Result |
| --- | --- |
| Backend authorization, authentication and integrity | 85 tests passed against isolated PostgreSQL 18.4; zero skips |
| PostgreSQL concurrency | Nine transaction race tests passed, covering dispensing/authorization, concurrent patient saves and provider suspension, and single-use email code verification, attempt limits and resend cooldown |
| Existing-account migration | Old authenticator enrollment retired; passwords, verified emails and sessions preserved; compact IDs backfilled with unique constraints and collision retry coverage |
| Real Chrome care workflow | All four roles signed in directly with email/password; cookie and CSRF authentication retained; compact IDs displayed for every role |
| Patient dashboard | No access-approval navigation; private photo upload, clickable and keyboard-operated card flip, QR and authenticated PDF download verified |
| Doctor visits and reports | Doctor found patient by compact ID without a patient permission request; consultation, linked prescription and report were visible in the patient visit log; standalone reports remained in the complete library |
| Persistence and pharmacy | Visit/report history survived reload; pharmacy dispensed 4 of 10 items, leaving 6; pharmacy and admin were denied clinical records outside their roles |
| Registration and email verification | All three public role signups, six-digit email codes, existing unverified accounts and resend cooldown passed through real browser/API calls with isolated file email delivery |
| Admin approvals | Separate doctor/pharmacist queues, document review, approval, rejection, history and professional access transitions passed |
| Desktop and mobile regressions | All 10 Playwright public-page, signup-layout and email-verification checks passed |
| Visual inspection | Card front/back, photo, visit log and report library inspected at desktop and 390-pixel mobile widths; no horizontal overflow |
| Frontend checks | Production build, TypeScript and ESLint passed |
| Production settings | `scripts/check-production.py` passed with zero issues using synthetic settings |
| Doctor data migration | Clinic 0004 rehearsed on a temporary Neon branch, then applied through the saved direct application connection; existing account IDs, sessions, clinical records and historical doctor-patient associations preserved |
| Migration rehearsal | Applied accounts 0005/0006 and clinic 0003 to a temporary Neon branch; existing accounts, passwords, verified emails, sessions, health IDs and clinical row counts were preserved |
| Connected application database | Rehearsed migrations applied through the saved direct Neon connection; all five existing accounts received valid unique compact IDs; existing records preserved; no model drift |
| Local application restart | Normal frontend on port 3000 and Django on port 8000; login returned HTTP 200 and readiness reported PostgreSQL healthy |
| Email settings | Saved Gmail SMTP configuration preserved; obsolete authenticator encryption setting removed; no real email sent by these checks |

The temporary Neon rehearsal branch was deleted after the application migration succeeded. Clinical mutations, uploads and registration tests used synthetic data in the explicit isolated test databases. The normal application has no SQLite fallback. Screenshots, PDFs and result files remain local under `.local/browser-workflow/` and `.local/registration-workflow/` and `.local/doctor-workflow/`, which are excluded from source control.

## Reproduce browser verification

From the repository root, with installed dependencies and Google Chrome available:

```powershell
.\.venv\Scripts\python.exe scripts/seed-e2e.py
# Terminal 1
.\.venv\Scripts\python.exe backend/manage.py runserver 127.0.0.1:8001 --settings=config.e2e_settings --noreload
# Terminal 2
$env:API_INTERNAL_URL='http://127.0.0.1:8001'
npm --prefix frontend run dev -- --port 3001
# Terminal 3
node scripts/browser-workflow.mjs
node scripts/doctor-workflow.mjs
node scripts/registration-workflow.mjs
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3001'
npm --prefix frontend run test:e2e -- --workers=1
```

The seed command writes only to the explicitly checked `.local/e2e.sqlite3` path and creates fresh synthetic identities. Reseed before rerunning the mutating care workflow. Stop both test servers afterward; use a fresh terminal, or remove the `API_INTERNAL_URL` override, before starting `npm run dev` for the normal application.

For PostgreSQL tests, use `compose.test.yaml` as described in the README. Without Docker, set `TEST_DATABASE_URL` to a disposable PostgreSQL instance and run `npm run test:backend`; its role must be able to create a separate test database. Do not point tests at the application database.

## Checks beyond this session

- Gmail STARTTLS authentication passed during SMTP setup. Actual inbox delivery still needs a normal user registration; synthetic tests use file email delivery.
- Container launch, an external HTTPS deployment and a live backup/restore drill have not been run on this machine. Deployment and backup procedures remain in `OPERATIONS.md`.
- Credential uploads have quarantine, signature checks and reviewer approval; an automatic antivirus scanner is not bundled.
- Generated PDFs use ReportLab standard fonts. Printed non-Latin scripts need embedded fonts and shaping validation.

See [SESSION_CHANGES.md](SESSION_CHANGES.md) for the completed user-facing changes.

## Doctor dashboard verification, 29 September 2026

- Full PostgreSQL suite: **85 passed, zero skipped**, including nine concurrency tests.
- Complete existing care workflow passed with all four roles, photo/card, consultations, prescriptions, uploads and pharmacy boundaries.
- Final two-doctor browser workflow passed: camera health-card QR opens history automatically and stops its camera tracks; compact ID lookup opens the same patient; lookup alone does not save patients.
- Explicit Add patient creates one persistent entry only in the requesting doctor's list; repeated saving does not duplicate it. Navigation back to the saved list and opening its record passed.
- Other-doctor consultations and private reports were readable; cross-author corrections and direct update/delete attempts were denied. A new consultation and report preserved the earlier record content.
- Doctor profile name and phone persisted after reload; email/account ID/role mutations were rejected. Shared password/session controls were present. Loaded doctor profile and saved-patient views passed 390-pixel mobile overflow checks and visual inspection.
- The QR test uses a synthetic camera stream with changing card size to exercise alignment; a physical webcam was not available for hardware testing. Patient ID remains the alternative to camera scanning.
- Final production build, TypeScript and ESLint passed. Production configuration sanity checks passed.
- Clinic migration 0004 was rehearsed on a temporary Neon branch, applied to the linked database, and checked for preservation of existing accounts, IDs, sessions and clinical records. The temporary branch was deleted.
- Normal app restarted on ports 3000/8000. Login returned HTTP 200 and readiness confirmed PostgreSQL healthy; saved Gmail settings remain intact.

Usage: [DOCTOR_DASHBOARD.md](DOCTOR_DASHBOARD.md). Browser evidence: `.local/doctor-workflow/results.json` and screenshots in that directory. The optional experimental QR image upload is not included; the shipped choices are camera scanning and ID entry.

## Patient dashboard metrics verification, 29 September 2026

- Full frontend browser suite: **42/42 passed** (21 desktop and 21 mobile), including 20 new dashboard scenarios. Final TypeScript, ESLint and production Next.js build passed.
- Full isolated PostgreSQL suite: **109 tests passed, zero skipped**, including authorization, tracking constraints, score-policy calculation, latest-per-test laboratory summaries, corrections retaining original measurement dates, and existing concurrency checks.
- Migration 0005 was rehearsed on a temporary Neon branch and applied to the linked application database. Account credentials, IDs and existing clinical records were preserved. The adherence and laboratory tables began empty; no invented health data was seeded. The temporary branch was deleted after verification.
- Live patient browser check passed: real dashboard counts and BP readings, unavailable score/adherence/lab states, six detail dialogs, health-card QR flip, medical timeline navigation, mobile overflow check and logout. No clinical data was changed in this check.
- Desktop and mobile screenshots were visually reviewed. New tracking forms and all dashboard click paths are also exercised with synthetic API fixtures so browser form tests do not alter the application database.
- Health scoring stays unavailable until a reviewed calculation policy and required fresh observations exist. Regional alerts stay unavailable until a reviewed source adapter is connected. Dose-log adherence and laboratory reference comparisons calculate directly from saved observations.

Usage and API details: [PATIENT_HEALTH_DATA.md](PATIENT_HEALTH_DATA.md). Read-only live browser check: `.local/check-patient-dashboard-live.mjs`; live screenshots: `.local/patient-dashboard-live-desktop.png` and `.local/patient-dashboard-live-mobile.png`.

## Continuous dashboards verification, 29 September 2026

- Full desktop/mobile browser suite: **70/70 passed**. After the final doctor-profile verification-state fix, **2/2 focused regression tests passed**. Final global ESLint, TypeScript and production Next.js build passed.
- Patient, doctor, pharmacist, and administrator dashboards render their primary sections on one page with persistent sidebar links and automatic scroll highlighting. Section hashes, Back/Forward, keyboard focus, reduced-motion preferences, sticky mobile offsets, and desktop sidebar overflow are handled by one navigation hook.
- Patient Dispensing history precedes My profile. Repeated navigation buttons, inner section headings, report libraries, and photo-edit controls were consolidated. Profile photo editing is in My profile; saved metadata updates the already-mounted health card.
- The pharmacist has one patient lookup section containing both ID entry and camera scanning. Provider clinical sections still require current approval; QR deep links open the correct section. Navigating away from the scanner unmounts it without clearing patient lookup state.
- Both admin approval queues remain mounted with independent filters and draft decisions. Credential evidence and approval-blocker IDs are unique across simultaneous queue details. Existing admin section routes remain supported.
- Focused browser runs passed for patient/admin functionality (44 checks) and doctor/pharmacy/admin navigation (16 checks). Tests intercepted all API requests and blocked unknown endpoints; their simulated submissions did not touch the linked database or email service.
- Read-only live browser checks passed for all four test accounts: section order, correct navigation/highlighting, responsive layout, and logout. Clinical records, approvals, and accounts were not changed. Desktop/mobile screenshots were visually reviewed.
- Doctor professional details now use the shared current application, so resubmitted credentials immediately show the pending status and clinical sections return to the approval gate.

Usage: [DASHBOARD_NAVIGATION.md](DASHBOARD_NAVIGATION.md). Live smoke script: `.local/check-workspace-scroll-live.mjs`; screenshots: `.local/workspace-{role}-live-{desktop,mobile}.png`.

## Scanner recovery verification, 29 September 2026

- Reproduced the reported failure in the actual in-app browser: `NotAllowedError: Permission denied by system`. After the user enabled Windows camera access, the physical webcam preview played at 640 x 480 without a permission error. The final implementation was checked again with the physical camera, then navigation away removed the preview; the app was left on Find patient with the camera closed.
- All **22 focused desktop/mobile scanner checks passed**. The tests decode a synthetic QR through the installed decoder for both doctors and pharmacists, verify one patient lookup, and require acquired camera tracks to stop. Error classification, retry after system denial, actual playback rejection, delayed permission completion, close before playback, reopening, and starting from a partially visible section are covered without physical camera or database access.
- All **18 dashboard navigation regression checks passed**. A final two-case desktop/mobile check also verified that a camera started while the previous section was highlighted stops when scrolled out of view.
- Camera startup errors now distinguish system and site permissions, missing hardware, and a busy/unavailable device. The UI includes Retry camera and expandable browser error details. The scan frame follows the preview size.
- Camera cleanup is serialized across attempts and uses the library state instead of waiting for the video playing flag. A reader-local video adapter handles the installed library's ignored play promise, so late cancellation is harmless and genuine playback failures still show an error. No global browser APIs or rejection handlers are replaced.
- Global ESLint, TypeScript and the production Next.js build passed.

Usage and troubleshooting: [DOCTOR_DASHBOARD.md](DOCTOR_DASHBOARD.md). Regression tests: `frontend/tests/health-card-scanner.spec.ts`.

## Report-backed patient demonstration, 30 September 2026

- Generated 60 original two-page monthly BP/fasting-glucose PDFs for the first
  five mapped synthetic patients: 12, 6, 24, 12 and 6 months. All 60 files passed
  page-count, identity, reading-average, glucose and dose-diary round-trip checks.
  Representative pages, including a 31-day diary, were rendered and visually
  reviewed without clipping or overlap.
- Additive migrations 0006/0007 and the 60-report import were rehearsed on a
  temporary Neon branch. A repeated import created no duplicates. The final
  import was committed to the existing synthetic database; a database
  fingerprint confirmed that all login identities, the five patient profiles
  and every other patient's clinical rows were preserved.
- The normal environment received compatible additive schema changes but no
  synthetic patient enrichment. Structured PDF extraction and the custom demo
  score are enabled only by synthetic settings. Risk level was removed from
  the patient UI globally.
- **137 PostgreSQL backend checks passed**, including authentication and
  dispensing concurrency, report access isolation, invalid-upload rollback,
  observation provenance, half-up scoring, stale/missing data, and dose-log
  corrections. The local disposable PostgreSQL instance was stopped afterward.
- Larger histories exposed repeated queries in visits and prescriptions. These
  lists now batch-load provider details, medicine totals and allergies. A
  regression compares one consultation with 25 and verifies that the query
  count stays constant while the returned prescription balances and allergies
  remain correct. Permission checks and locking rules are preserved.
- **40 patient browser cases covered** across desktop/mobile focused runs;
  TypeScript, ESLint and the optimized Next.js build passed. Score/adherence
  dialogs expose actual inputs, formula and report links. Uploading a report
  refreshes the already-mounted overview.

Fixture and formula: [PATIENT_REPORT_DEMO.md](PATIENT_REPORT_DEMO.md).
Live verification script: `scripts/verify-first-five-patients.mjs` (sign-in/out
and report access create normal audit events; its five downloads increment the
corresponding actual download counters).

Final live run passed for all five accounts. It matched all 60 served PDF
hashes to their source files, checked complete doctor consultations and linked
prescriptions, recalculated score/adherence independently, checked report and
record counts, verified inline viewing and attachment downloads, and rejected
cross-patient report requests. The first patient's real score/adherence dialogs
and report library were also visually reviewed. Results and screenshots are in
`.local/first-five-dashboard-verification/`. Both local servers remain running;
the five enriched patients belong to port **3001**.
