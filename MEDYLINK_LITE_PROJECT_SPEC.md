# MedyLink — Project Build Specification

**Purpose:** Build a smaller MedyLink with real authentication, a digital health card, shared patient records, verified doctors, and verified pharmacy shops.

**Reference:** [Aashutosh-Mahajan/ArogyaTrack](https://github.com/Aashutosh-Mahajan/ArogyaTrack).

**Reviewed:** 28 September 2026. This specification is based on reading a downloaded snapshot of the repository's `main` branch, including dependency manifests and implementation files. The reference application was not executed or security-certified. Repository links below follow `main` and may change.

**Deliverable:** A build specification for a new application. Requirements below describe the proposed application; they are not claims that the original repository implements every requirement.

## 1. Product goal and boundaries

Create one responsive web application where a patient maintains one health identity and one longitudinal medical history. A verified doctor can access that history with the patient's approval and add a consultation or prescription. A verified pharmacy can view an approved prescription and record medicines dispensed. Records remain available across providers through the same backend and database.

Use the original project's core technology families: **Next.js, React, TypeScript, Tailwind CSS, Django, Django REST Framework, SimpleJWT, and PostgreSQL**. Keep the useful QR and PDF libraries. Remove machine learning and unrelated modules.

### First-release assumptions

- Web only, responsive on phones, tablets, and computers; no separate mobile or legacy admin application.
- Four roles: `patient`, `doctor`, `pharmacist`, and `admin`. One role per account in this release.
- One patient profile per patient account; self-managed adult patients only. Family profiles, guardians, and emergency access are later features.
- One pharmacy shop and one named, verified pharmacist account per shop initially. No shared staff password.
- Email and password sign-in, verified email, password recovery, and production email delivery. Phone number is a contact field; SMS sign-in is deferred.
- Doctor and pharmacy credentials are reviewed manually by an administrator. Registration does not automatically approve a provider.
- English interface initially. Store Unicode text so names and notes are not restricted to English.

### Meaning of “available to all verified doctors and pharmacy shops”

Any verified provider on the platform is eligible to request access, including a doctor or pharmacy that has never treated that patient before. The patient approves the particular provider and access scope. This is the recommended sharing policy for this specification, rather than a requirement explicitly supplied by the user.

Doctors receive a time-limited view of the shared clinical history. Pharmacies receive only the selected prescription, basic identity needed to match the patient, and allergy information. Verification alone does not reveal every patient's records. A printed or photographed QR code is an identifier, never permission to read medical data.

## 2. What was learned from the reference project

| Area inspected | Existing implementation | Decision for the smaller application |
| --- | --- | --- |
| [Frontend manifest](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/frontend/package.json) | Next.js `^14.1.0`, React `^18.2.0`, TypeScript `^5.3.3`, Tailwind `^3.4.1`; Radix components, React Query, Zustand, Axios, React Hook Form, Zod | Keep this frontend approach with compatible, supported dependency versions. |
| [Backend manifest](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/requirements.txt) | Django `>=4.2,<5.0`, DRF `>=3.14`, SimpleJWT `>=5.3`, PostgreSQL driver, Redis, Celery, QR and PDF packages | Keep the Django REST API and PostgreSQL. Remove ML packages and defer Celery. |
| [Authentication](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/accounts/authentication.py), [browser API client](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/frontend/lib/api.ts), and [UI auth store](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/frontend/store/authStore.ts) | Cookie JWT authentication exists; the frontend sends credentials and keeps UI identity separately from tokens | Retain cookie authentication, enforce CSRF consistently, and make the backend authoritative. |
| [Patient models](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/patients/models.py) | Patient IDs, multiple family profiles, consent fields, health cards with signed JWTs and revocation | Keep a single patient profile and printable card; use a replaceable opaque card identifier and explicit access approval. |
| [Medical models](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/medical/models.py) | Medical records, visit records, allergies, conditions, and time-limited `DoctorPatientAccess` | Use one encounter model and one shared-access model for clearer ownership and fewer overlapping concepts. |
| [Prescriptions](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/prescriptions/models.py) and [pharmacy](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/pharmacy/models.py) | Prescription items, dispensing records, medicine catalog, stock, and billing | Keep prescriptions and quantity-based dispensing; omit catalog management, inventory, invoices, and taxes. |
| [Pharmacy scanning](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/pharmacy/views.py) | Patient card/ID lookup and a response grouping prescriptions by doctor | Apply a patient-approved, prescription-specific pharmacy scope in the new design. |
| [Mobile manifest](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/mobile_app/pubspec.yaml) and `archive/legacy-vite-admin-panel/` | Flutter/Dart mobile app and an archived Vite interface also exist in the downloaded source | Defer both. Build all four role experiences inside the single Next.js application. |

The original also contains surveillance, adherence, AI/CDSS, dashboards, and reporting beyond this first release. Reuse the core workflow ideas without carrying those modules into the new application.

Specific production details to carry into the new design: the reference [account routes](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/accounts/urls.py) include multiple token/login paths, while its [account views](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/accounts/views.py) can return token JSON alongside cookies. Consolidate browser token issuance into one policy and omit token JSON. Its [pharmacist permission](https://github.com/Aashutosh-Mahajan/ArogyaTrack/blob/main/backend/accounts/permissions.py) checks the role; the new permission must also enforce professional/shop approval. Purpose-bound recovery challenges and mandatory production email configuration are explicit requirements below.

## 3. Technology stack and version policy

“Same tech stack” means retaining the frameworks and architecture, with maintained versions suitable for a new deployment. It does not mean copying old version ranges unchanged.

The reference pins Django below 5.0 and uses Next.js 14. Django 4.2 ended extended support on 7 April 2026, and Next.js lists 14.x as unsupported. Use **Django 5.2 LTS** and **Next.js 16.x** as the proposed starting baseline, with current security patches and compatible React, DRF, and SimpleJWT versions. Recheck support and compatibility when implementation begins. Sources: [Django support table](https://www.djangoproject.com/download/) and [Next.js support policy](https://nextjs.org/support-policy).

| Layer | Technology | Usage |
| --- | --- | --- |
| Web | Next.js App Router, React, TypeScript | One application with role-specific layouts and pages |
| UI | Tailwind CSS, shadcn/ui-style Radix components, Lucide icons | Forms, tables, dialogs, navigation, and accessible controls |
| Forms | React Hook Form and Zod | Client validation; DRF independently validates every request |
| API client and state | Axios, TanStack React Query; minimal Zustand where useful | Requests and transient UI state; no persistent medical-data or token store |
| Backend | Python, Django, Django REST Framework | A modular monolith with REST endpoints |
| Authentication | Django password hashing and SimpleJWT | Short-lived JWTs in protected cookies, refresh rotation, server-side revocation |
| Database | PostgreSQL and Django ORM | Accounts, patient history, access grants, prescriptions, audit events |
| Abuse protection | Redis | Shared rate-limit counters across backend workers; never the source of truth for medical records |
| QR | Python `qrcode`/Pillow and frontend `html5-qrcode` | Health-card generation and camera scanning |
| PDF | ReportLab | Downloadable health card and prescription |
| Email | Django email backend with a real SMTP service | Email verification and password recovery |
| Deployment | Docker, HTTPS reverse proxy, Gunicorn, Next.js production server | Reproducible deployment with private backend services |
| Provider documents | Private filesystem volume initially | Credential evidence served only through an authorized API |

Use supported Python and Node.js releases compatible with the chosen framework versions. Pin resolved production dependencies, commit the frontend lockfile and backend dependency lock, and review vulnerabilities before release. The original package ranges are evidence of its stack, not a tested installation recipe for the new application.

Small security/testing dependencies, such as a maintained TOTP package and browser test runner, may be added. These do not replace the core stack. Celery, cloud object storage, and a separate search service are not required for this initial scope.

## 4. Feature scope

### Build in the first release

1. Registration, email verification, login, logout, password reset, and session revocation.
2. Doctor and pharmacy credential submission, approval, rejection, resubmission, and suspension.
3. Patient profile, unique health ID, QR health card, PDF download, and card replacement.
4. Patient-approved doctor access and prescription-specific pharmacy access, with expiry and revocation.
5. Shared medical timeline: consultations, manually entered diagnoses, vitals, allergies, and chronic conditions.
6. Doctor-issued prescriptions, printable prescription, cancellation, and pharmacy dispensing history.
7. A small administrator verification console and patient-visible access history.
8. Persistent database storage, protected credential files, meaningful authorization tests, backups, and deployment documentation.

### Explicitly exclude from the first release

- All ML/AI, OpenAI integration, CDSS, automated diagnosis, risk scoring, outbreak detection, disease forecasting, and surveillance maps.
- `ml_models`, `surveillance`, `cdss`, model-training jobs, and their dependencies, including NumPy, pandas, scikit-learn, Prophet, XGBoost, and OpenAI SDK unless an unrelated future feature explicitly needs them.
- Medication reminders, adherence scoring, scheduled health alerts, and analytics dashboards.
- Flutter mobile development, the archived Vite app, offline records, and PWA caching of medical data.
- Stock/inventory, payments, billing, invoices, GST calculations, appointments, chat, and video consultations.
- Drug-interaction engines, automatic medicine suggestions, OCR, laboratory integrations, and diagnosis-code catalog management.
- Patient report uploads, bulk exports, family profiles, external health-ID integration, and automatic professional-register checks. These can be separate later increments.

Do not expose navigation or placeholder APIs for excluded features.

## 5. Roles and permissions

| Action | Patient | Verified doctor | Verified pharmacist/shop | Admin |
| --- | --- | --- | --- | --- |
| View/edit own account | Yes | Yes | Yes | Yes |
| View own patient profile/card | Yes | No | No | No routine access |
| Update patient demographics | Own profile | No | No | No |
| Request patient access | No | Yes | Yes, for dispensing | No |
| Approve/revoke patient sharing | Own data | No | No | No |
| Read clinical timeline | Own data | With active clinical grant | No | No routine access |
| Add consultation/prescription | No | With active clinical grant | No | No |
| Read selected prescription and allergies | Own data | With active clinical grant | With active dispensing grant | No routine access |
| Dispense prescribed items | No | No | Own approved shop, with active grant | No |
| Review provider credentials | Own submission only where applicable | Own submission | Own submission | Yes |
| Approve/suspend providers | No | No | No | Yes |
| View audit information | Own record-access history | Own permitted activity | Own shop's activity | Verification/security metadata |

Pending, rejected, suspended, and expired-verification providers cannot use patient-access endpoints. They may view their own application status and submit requested corrections. Administrative permission is not a general clinical-record permission. If Django Admin is enabled, restrict its model permissions accordingly.

Every list, detail, mutation, PDF, and document-download endpoint must enforce object-level access. Hiding links in the frontend is only a usability measure. The backend derives the actor and role from authentication, never from a submitted `doctor_id`, `pharmacy_id`, or `role` override.

## 6. Main user journeys

### 6.1 Patient registration and health card

1. Register with name, email, and password; accept a versioned privacy notice and consent to store records.
2. Receive a real verification email. Confirm the single-use link before access to patient features.
3. Enter date of birth and optional contact details, blood group, emergency contact, allergies, and chronic conditions. Unknown blood group is valid. Distinguish “unknown” allergy status from “no known allergies.”
4. Generate a unique health ID and health card after completing the required profile fields. Compute age from date of birth.
5. Display or download the card. Show name, health ID, and QR by default; additional printed personal details require patient choice. Never print full medical history.
6. View records, prescriptions, dispensing events, pending access requests, active grants, and access history.

The health ID is local to this application. Do not represent it as an official government health ID or require Aadhaar for this MVP.

### 6.2 Provider verification

1. A doctor submits name, registration number, registering body/jurisdiction, specialty, practice details, and credential evidence.
2. A pharmacist submits their professional details plus shop name, business/license details, contact address, license validity where applicable, and evidence.
3. Email verification establishes control of the email address only. The provider stays `pending` until manual credential review.
4. An administrator records the evidence reviewed, decision, reviewer, timestamp, reason, and applicable validity date.
5. Approval enables access requests. Rejection shows a reason and allows a new submission while preserving prior decisions.
6. Suspension or an elapsed verification validity date blocks protected requests immediately. Reapproval does not reactivate old revoked patient grants.

Verification-changing fields require review again. Users cannot edit their approved registration/license identity without returning that credential to a pending state. Bootstrap administrators through a controlled management command; there is no public admin registration or default password.

Keep one authoritative current verification submission per provider. Historical approvals never satisfy the permission check. Suspension or credential changes revoke active grants and pending requests. Bind approved grants to the current approval version so expiration followed by reapproval cannot revive earlier access.

### 6.3 Doctor consultation

1. The verified doctor scans the card or enters the exact health ID.
2. The API accepts an access request without revealing the patient's clinical details. There is no global patient directory or partial-name search.
3. The patient sees the doctor's verified identity, purpose, scope, and expiry, then approves or rejects the request.
4. An approved clinical grant lasts **24 hours by default** and can be revoked sooner. No WebSocket service is necessary; bounded polling or refresh is sufficient.
5. The doctor reads the shared timeline, including earlier entries from other doctors, and records the new encounter.
6. The doctor optionally issues a prescription. The patient immediately sees the finalized information.
7. Another verified doctor can repeat this flow and see the same longitudinal history after obtaining their own grant.

Finalized records retain their author and timestamp. A doctor may add a linked correction to their own record, with a reason and active grant; they cannot silently rewrite another doctor's entry. Patient-reported information must retain its source label.

### 6.4 Pharmacy dispensing

1. A verified pharmacist at an approved shop scans the health card or prescription QR, or enters the exact identifier.
2. The patient approves access to **one selected prescription** for that named pharmacist/shop, for **one hour by default**. A card scan can initiate the request; the patient selects the prescription before approval.
3. The pharmacy sees basic patient identification, the selected prescription, issuer details, allergy information with its source, and quantities remaining. It cannot see encounter notes, unrelated diagnoses, or other prescriptions.
4. The pharmacist enters quantities dispensed in the same units used on the prescription and confirms the handover.
5. The system records who dispensed what, where, when, and how much. Partial dispensing is supported.
6. A different verified pharmacy can dispense remaining quantities only after receiving its own approval. All pharmacies use the same remaining balance in PostgreSQL.

No inventory or billing system is required. The application records clinician-entered instructions; it does not generate dosage advice or claim to check drug safety.

## 7. Authentication and session requirements

Use one same-origin browser deployment: `/` serves Next.js and `/api/v1/` routes to Django behind the HTTPS proxy. Keep business logic and authorization in Django.

- Hash passwords with Django's maintained password-hashing system; apply password validators, allow long passwords, and never store or log plaintext passwords.
- Normalize email consistently and enforce case-insensitive uniqueness in PostgreSQL. Public registration accepts only the three public roles.
- Use actual email verification and recovery delivery. Development may use a console mail backend; production must refuse that configuration. Do not return verification or reset secrets from public APIs.
- Verification links expire after 24 hours; password-reset links expire after 30 minutes. Both are single-use, purpose-bound, and stored as digests where database storage is needed. Resending invalidates the previous outstanding link for that purpose.
- Send generic login/recovery errors and throttle registration, login, reset, verification resend, MFA, QR lookup, and access requests. Use shared Redis counters and deployment-level limits; do not rely only on per-process counters.
- Enable TOTP MFA for administrators, doctors, and pharmacists before privileged access; patients may opt in. Use a maintained library, protect TOTP secrets, and hash single-use recovery codes. Password reset must not bypass MFA. MFA recovery requires a documented identity-review process and revokes existing sessions.
- For a new account that requires MFA but has not enrolled, successful password/email checks issue only a short-lived restricted enrollment session. It may call MFA setup/confirmation and logout, never patient-data endpoints. Issue normal session tokens only after successful enrollment and factor confirmation. Already enrolled users receive a restricted MFA challenge until the factor succeeds; optional patient enrollment requires recent reauthentication.
- Issue a short-lived access JWT, proposed **10 minutes**, and a rotating refresh token with a maximum session duration of **7 days**. Check live account status, verification, and access grants on protected requests.
- Keep one token-issuance policy. Do not expose stock token endpoints or alternate OTP login paths that skip email verification, MFA, or active-account checks. Pre-MFA challenges expire after five minutes, are single-use and purpose-bound, and cannot authenticate patient-data requests.
- Set JWTs only in `HttpOnly`, `Secure`, host-only cookies with an appropriate `SameSite` policy. Do not return browser token copies in JSON or store them in local/session storage, URLs, QR codes, or persisted Zustand state.
- Configure CSRF enforcement for cookie-authenticated requests and authentication mutations, including login, refresh, and logout. Obtain a CSRF token through a bootstrap endpoint and send it in a header; that CSRF cookie may be readable by JavaScript. SameSite cookies alone are insufficient.
- Enable SimpleJWT refresh rotation and blacklisting. Add a database-backed `AuthSession` referenced by a JWT `sid` so logout, password reset, account suspension, and “log out all devices” can invalidate access tokens before they expire. Rotation/replay handling must be atomic per session; do not hand-roll JWT cryptography.
- Require the session's original absolute expiry on every refresh; rotation must not extend the seven-day maximum indefinitely. Clear cookies with matching path/domain attributes on logout.
- On page load, hydrate identity from `/auth/me/`. Clear React Query state and sensitive in-memory content on logout or account change. Do not treat a persisted `isAuthenticated` flag as proof of authentication.

SimpleJWT documents token lifetimes, rotation, and its blacklist app, but cookie transport, complete CSRF handling, MFA, session-family revocation, and the business access policy need explicit integration and tests. See [SimpleJWT settings](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/settings.html).

## 8. Health card and patient sharing design

Use a cryptographically random, opaque card locator with at least 128 bits of randomness. Example QR shape: `https://app.example/health-card/<opaque-locator>`. It contains no diagnosis, email, phone number, or authentication JWT.

- A public scan opens only a generic sign-in/request-access page. It does not display patient information.
- After authentication, a verified provider can submit a scoped request using that locator. The patient approves from their own authenticated account; physical possession of the card is not approval.
- An exact health ID is a fallback for camera failures and follows the same consent checks. Make lookup responses non-revealing, throttle attempts, and prevent bulk enumeration.
- Provide card replacement. Rotate the locator and reject old locators; in the same operation revoke active grants and cancel pending requests for that patient. Keep the stable health ID.
- A grant binds patient, named provider, scope, purpose, approval time, and expiry. Pharmacy grants additionally bind shop and prescription. Scope and resource IDs cannot be expanded after approval.
- Store the policy/notice version accepted by the patient. Separate agreement to store records from approval to share with a particular provider.
- Expiry is checked against server time on every request; it must work even if no scheduled worker is running.
- Downloads use the same authorization rules as JSON endpoints. Revocation prevents subsequent access; the interface must accurately explain that previously downloaded or printed copies cannot be recalled.

Default authorization rule for clinical data:

```text
allow = authenticated account with active session
        AND (patient owns the data
             OR (provider is currently verified and active
                 AND approved grant is unexpired and not revoked
                 AND grant matches this patient, provider, resource, and action))
```

Audit protected reads, writes, downloads, grant decisions, and denied access. Avoid logging raw card locators, credentials, medical notes, or full request bodies.

## 9. Minimal data model

Use UUID primary keys, UTC timestamps, database constraints, and migrations. Foreign keys preserve relationships across all providers. The names below are proposed new models, not a requirement to copy the reference schema.

| Entity | Main fields and relationships |
| --- | --- |
| `User` | UUID, normalized email, Django password hash, role, active status, email verification timestamp, MFA state |
| `AuthSession` | UUID, user, creation/absolute expiry, revoked timestamp, refresh-family state, last-used timestamp; JWTs carry the session ID |
| `AccountToken` | User, purpose, token digest, expiry, consumed timestamp for verification/recovery |
| `PatientProfile` | One-to-one user, unique health ID, name, DOB, optional gender/blood group/contact/emergency contact, privacy-notice version and storage-consent time |
| `DoctorProfile` | One-to-one user, registration number plus registering body/jurisdiction, specialty and practice details |
| `Pharmacy` | UUID, one-to-one pharmacist user for this release, shop name, address, license number/jurisdiction, validity, active status |
| `ProviderVerification` | Provider, submission version, professional/shop credential details, private evidence file metadata, status, reviewer, reviewed time, reason, valid-until; retain decision history |
| `HealthCard` | One-to-one patient, unique opaque locator, issued time, replaced/revoked time; PDF/QR can be generated on demand |
| `AccessGrant` | Patient, provider, provider approval version, optional pharmacy and prescription, scope (`clinical` or `dispensing`), purpose, status (`pending`, `approved`, `rejected`, `revoked`), requested/approved/expiry/revoked times, policy version |
| `MedicalRecord` | Patient, author doctor, visit time, symptoms, manually entered diagnosis, notes, optional structured vitals, finalized time; optional `corrects_record_id` and correction reason |
| `Allergy` / `ChronicCondition` | Patient, manually entered description, reaction where relevant, source (`patient_reported` or `doctor_recorded`), author, recorded time, optional supersedes link; retain changes |
| `Prescription` | Patient, author doctor, optional encounter, issued time, clinician-selected valid-until, cancelled time/reason, opaque lookup reference |
| `PrescriptionItem` | Prescription, medicine name, strength/form, dosage instructions, frequency, duration, prescribed quantity and unit; snapshot text, no medicine catalog required |
| `DispenseEvent` | Prescription, pharmacy, pharmacist, timestamp, unique idempotency key within pharmacist scope, request digest |
| `DispenseItem` | Dispense event, prescription item, quantity and unit; positive quantities only |
| `AuditEvent` | Actor, patient/resource references where applicable, event type, time, outcome, request ID, minimal security metadata; append-only to application users |

### Required integrity rules

- Create a custom user model before the initial migration. Enforce one patient profile and one public role per account.
- Generate health IDs with a secure random suffix and a database unique constraint; retry collisions after `IntegrityError` rather than relying only on a pre-insert existence query.
- Validate dates, field lengths, file limits, role-specific fields, and quantity units server-side. All clinical fields are entered by humans; validation does not generate diagnoses.
- Enforce unique provider credential identifiers within the registering jurisdiction/body. Duplicate credentials go to manual review; registering another email must not automatically create a second approved identity.
- Grant approval verifies that the patient owns the requested record and, for dispensing, that the chosen prescription belongs to that patient. Use separate serializers for clinical and pharmacy views.
- An encounter's doctor and a dispense event's pharmacist/shop are assigned from the authenticated account. Reject references to objects outside the authorized patient/prescription.
- Preserve finalized clinical content and attribution. Patients can update their own demographics and patient-reported entries; they cannot change clinician-authored content.
- Keep cancellation separate from dispensing progress. Compute `issued`, `partially_dispensed`, or `fulfilled` from quantities; show `cancelled` or `expired` when further dispensing is blocked. Preserve completed dispensing history.
- Use positive decimal quantities with an explicit unit consistently on prescribing and dispensing. Do not infer tablet counts from a dosage string. No automatic unit conversion, substitutions, or refill cycles in this release.
- Protect clinical and audit relationships from cascading account deletion. Account closure disables access; any retention/deletion process is a separately documented operation, not a generic CRUD delete.

### Dispensing transaction

Inside `transaction.atomic()`, lock the prescription and its relevant items using `select_for_update()` in a consistent order. Cancellation uses the same prescription lock. Validate current provider/shop status, the active grant, prescription validity, and remaining quantities immediately before saving. Serialize grant revocation with protected mutations where necessary so a transaction cannot commit using an already-revoked grant.

Store the event and all items atomically. The sum dispensed across **all pharmacies** must never exceed the prescribed quantity. A retry using the same idempotency key and payload returns the existing result; reusing that key with a different payload returns a conflict. Check current authorization before returning a replayed result. Test this behavior against PostgreSQL with concurrent transactions.

Reject duplicate prescription-item IDs within a single request and enforce a unique `(dispense_event, prescription_item)` constraint. Every submitted item must belong to the locked prescription; validate the entire batch before writing any items.

## 10. API outline

Prefix all endpoints with `/api/v1`. This is the proposed API, not an inventory of the reference API. Publish an OpenAPI schema while building. Pagination and bounded page sizes apply to every list.

| Area | Endpoints | Main access rule |
| --- | --- | --- |
| Registration | `POST /auth/register`, `POST /auth/verify-email`, `POST /auth/resend-verification` | Valid public role; verification/resend abuse controls |
| Login/session | `GET /auth/csrf`, `POST /auth/login`, `POST /auth/mfa/verify`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | CSRF on authentication mutations; full tokens only after all required factors |
| Recovery/security | `POST /auth/forgot-password`, `POST /auth/reset-password`, `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `POST /auth/logout-all` | Purpose-bound recovery; sessions restricted to their owner |
| MFA setup | `POST /auth/mfa/setup`, `POST /auth/mfa/confirm`, `POST /auth/mfa/recovery-codes` | Recent reauthentication; recovery-code regeneration invalidates old codes |
| Patient profile/card | `GET/PATCH /patients/me`, `GET /patients/me/card`, `GET /patients/me/card.pdf`, `POST /patients/me/card/replace` | Patient owns profile; idempotent generation |
| Own patient history | `GET /patients/me/records`, `GET /patients/me/prescriptions`, `GET /patients/me/dispensing`, `GET /patients/me/access-history` | Owner only |
| Clinical summaries | `GET/POST /patients/{id}/allergies`, `GET/POST /patients/{id}/conditions` | Patient owns data or doctor has active clinical grant; source determined server-side |
| Sharing | `POST /access-requests`, `GET /access-requests`, `POST /access-requests/{id}/approve`, `POST /access-requests/{id}/reject`, `GET /access-grants`, `POST /access-grants/{id}/revoke` | Provider requests; patient owns approval/revocation; lists scoped to participant |
| Doctor work | `GET /doctor/patients`, `GET /patients/{id}/clinical-summary`, `GET/POST /patients/{id}/records`, `POST /records/{id}/corrections` | Current verification plus active patient grant; patient list contains only currently authorized patients |
| Prescriptions | `POST /patients/{id}/prescriptions`, `GET /prescriptions/{id}`, `GET /prescriptions/{id}/pdf`, `POST /prescriptions/{id}/cancel` | Authoring/cancellation by issuing doctor with grant; read rules depend on owner/provider scope |
| Pharmacy work | `GET /pharmacy/me`, `GET /pharmacy/shared-prescriptions`, `POST /prescriptions/{id}/dispense`, `GET /pharmacy/dispensing` | Approved named pharmacist and shop; selected-prescription grant for new reads/dispensing |
| Provider application | `GET/POST /provider/application`, `POST /provider/application/documents` | Own submission only; new versions preserve review history |
| Administration | `GET /admin/provider-applications`, `GET /admin/provider-applications/{id}`, `POST /admin/provider-applications/{id}/approve`, `POST /admin/provider-applications/{id}/reject`, `POST /admin/providers/{id}/suspend`, `GET /admin/audit` | Administrator with MFA; no automatic clinical-data access |
| Evidence download | `GET /provider-documents/{id}/download` | Submitting provider or credential reviewer only |

Use a consistent error body such as `{ "code": "access_expired", "detail": "Request patient access again.", "request_id": "..." }`. Use `401` for missing/invalid authentication, `403` for known forbidden actions, `404` where needed to hide inaccessible resources, `409` for state/idempotency conflicts, and `429` for throttling.

Lists, counts, PDFs, and error responses must respect the same field-level privacy rules as record detail endpoints. A pharmacy's own historical dispensing log can retain a minimal immutable transaction snapshot after a grant ends; it must not become a route back into the patient's current clinical data.

## 11. Screens and interface behavior

| Role | Required screens |
| --- | --- |
| Public/account | Landing page, registration by role, login, email verification, password recovery, MFA challenge |
| Patient | Overview, profile, health card, medical timeline/detail, prescriptions/detail, dispensing history, sharing requests/grants, access history, security settings |
| Doctor | Verification status, currently shared patients, scan/manual ID entry, patient clinical summary, encounter entry, prescription entry, security settings |
| Pharmacist | Shop/application status, scan/manual ID entry, approved prescription view, dispense form, shop dispensing history, security settings |
| Admin | Provider review queue, application/evidence detail, approval/rejection/suspension controls, security audit metadata, security settings |

Use familiar layouts from the reference: sidebar on desktop, compact navigation on mobile, readable cards, simple tables, and clear status badges. Reuse form and table components. Avoid decorative analytics charts for information that fits in a count or list.

Every screen needs loading, empty, validation, expired-session, denied-access, and request-failure states. Camera access must be optional; manual ID entry provides the fallback. Stop camera streams when leaving the scan screen. Keep keyboard navigation, labels, focus management, and sufficient contrast.

Patient-facing language should explain who will see what and for how long. Show the provider's verified name and shop where relevant before approval. Disable duplicate submission in the UI while retaining server-side idempotency for dispensing. No hard-coded demo records, fabricated counts, or success messages before the API succeeds.

## 12. Suggested project structure

```text
medylink-lite/
  backend/
    config/                 # Settings, URLs, WSGI
    accounts/               # Users, authentication, sessions, MFA, verification
    patients/               # Profiles, cards, shared-access policy
    medical/                # Encounters, corrections, allergies, conditions
    prescriptions/          # Prescription items and lifecycle
    pharmacy/               # Shop identity and dispensing
    audit/                  # Security and clinical-access events
    tests/                  # Cross-module authorization and concurrency tests
    manage.py
    requirements.txt
    requirements.lock
    .env.example
    Dockerfile
  frontend/
    app/
      (auth)/
      patient/
      doctor/
      pharmacy/
      admin/
    components/             # Shared UI, forms, scanner, card
    lib/                    # API client, validation, formatting
    store/                  # Minimal transient UI state
    types/
    tests/
    package.json
    package-lock.json
    .env.example
    Dockerfile
  deploy/                   # HTTPS proxy and operational examples
  docs/                     # API, setup, permission matrix, backup/restore
  docker-compose.yml
  README.md
```

Keep permission functions reusable and call them from both view/query filtering and mutation services. Use transactions for multi-record writes. Do not introduce microservices, event buses, a separate Node backend, or a second database.

## 13. Production configuration and operations

Deploy one Next.js service, one Django/Gunicorn service, PostgreSQL, Redis, and an HTTPS reverse proxy. Use a private persistent volume for provider evidence. Add a private object store only when deployment topology requires it. Production database/Redis ports and evidence files must not be publicly exposed.

Required configuration includes `DJANGO_SECRET_KEY`, a separate `JWT_SIGNING_KEY`, database/Redis connection settings, allowed hosts, CSRF trusted origins, canonical frontend origin, SMTP credentials/from address, cookie settings, private storage location, and MFA-secret protection key. Public frontend variables contain only public configuration such as the `/api/v1` base path. Provide placeholder-only `.env.example` files and keep real secrets outside Git.

- Configure production to fail closed when secrets or required email/storage settings are absent. Use `DEBUG=False`, HTTPS, trusted proxy settings, and explicit host/origin allowlists.
- Enforce CSRF and secure cookies, deploy a compatible Content Security Policy, and use `Cache-Control: no-store` for authenticated medical responses and downloads. Avoid shared/CDN caching of personalized pages; use a restrictive referrer policy for QR routes.
- Allow only bounded PDF/JPEG/PNG credential uploads; check file signatures as well as extensions, generate server-side names, and quarantine until validation/malware scanning succeeds. Do not execute or publicly serve uploads. Authorized download checks run for every request.
- Avoid clinical details and authentication secrets in application logs, analytics, error tracking, and email. Audit critical mutations in the same transaction; protect audit events against application-level edits/deletion and back them up.
- Encrypt database disks, private storage, and backups. Use least-privilege database/storage credentials and a secrets-management procedure appropriate to the hosting platform.
- Take automated database and document backups; agree recovery targets and demonstrate restoration into an isolated environment before launch. Monitor API failures, email delivery failures, storage capacity, and backup failures.
- Document deployment, migration ordering, rollback, credential rotation, provider suspension, and incident response. Run schema migrations once per release, not concurrently from every replica.
- Keep email sending bounded by timeouts and provide resend/retry handling. A future Celery worker may improve delivery reliability, but it is not needed for ML or reminders in this scope.

Use the [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) and run `manage.py check --deploy` with production settings. These engineering requirements are not a certification of compliance with healthcare or privacy law; operating policies and applicable retention obligations must be settled before using real patient data.

## 14. Implementation phases and exit criteria

| Phase | Work | Exit criterion |
| --- | --- | --- |
| 1. Foundation | Supported dependency set, Django/Next setup, PostgreSQL migrations, Docker development setup, environment templates | Both services start, API health check passes, and data survives restart |
| 2. Accounts and verification | Registration, real email, cookies/CSRF, MFA, revocable sessions, provider application and admin review | Patient can authenticate; pending providers cannot read patient data; approved providers can request access |
| 3. Identity and sharing | Patient profile, QR/PDF card, scoped approval/expiry/revocation, audit events | A second verified doctor can access the same patient only after approval; a copied QR alone reveals no medical data |
| 4. Clinical records | Shared timeline, sourced allergies/conditions, encounters/corrections, prescriptions/PDF | Doctor A's finalized entry is visible to the patient and an authorized Doctor B, with original attribution intact |
| 5. Pharmacy | Verified shop, prescription-specific sharing, partial dispensing, idempotency and locking | Two pharmacies share the same remaining quantity without duplicate or excess dispensing |
| 6. Release readiness | Role/API tests, browser workflow, deployment checks, dependency review, backup restoration, setup/runbook | Acceptance criteria below pass in a production-like environment |

Implement each phase end to end with real backend integration. Keep security checks in the phase that introduces the data flow; do not defer all authorization until the last phase.

## 15. Acceptance criteria

### Functional

- [ ] Registration persists a real account; email verification and password reset work through the configured delivery service.
- [ ] Login, refresh, logout, session revocation, MFA, and recovery survive page reloads without browser-stored bearer tokens.
- [ ] Doctor and pharmacy access stays blocked until their respective credential reviews are approved.
- [ ] Each patient has one stable health ID and a usable downloadable QR health card.
- [ ] Doctor A can add a record and prescription; Doctor B can see the shared history after separate patient approval.
- [ ] The patient sees author, date, corrections, prescriptions, and dispensing events in their own portal.
- [ ] An approved pharmacy sees only the selected prescription and permitted patient fields.
- [ ] Partial dispensing updates the remaining quantity across shops; repeated submission does not duplicate an event.
- [ ] Data persists across browser refresh, application restart, and a tested backup restore.
- [ ] No ML/AI service, key, model file, or excluded-module placeholder is required to build or run the application.

### Authorization and data integrity

- [ ] Unauthenticated users and QR holders cannot retrieve patient details, records, PDFs, or provider evidence.
- [ ] Changing patient, record, prescription, grant, document, or shop IDs in direct API requests does not bypass authorization.
- [ ] A revoked/expired grant or suspended provider loses access on the next protected request; mutation/revocation races are covered.
- [ ] Public users cannot assign themselves admin status or alter their verification result.
- [ ] Pharmacy serializers and PDFs omit clinical notes and unrelated records, even when an endpoint is called manually.
- [ ] Patients cannot rewrite doctor-authored content; doctors cannot silently edit another doctor's finalized records.
- [ ] Logout/password reset/session revocation invalidate the relevant access and refresh credentials server-side.
- [ ] Cookie-authenticated mutations, login, refresh, and logout reject missing or invalid CSRF proof.
- [ ] Reset/verification links and MFA recovery codes cannot be reused; MFA cannot be skipped through a fallback endpoint.
- [ ] Two simultaneous pharmacy requests cannot dispense more than the prescribed balance; cancellation races and idempotency conflicts are tested on PostgreSQL.
- [ ] Cancelled, expired, and fully dispensed prescriptions reject further dispensing.
- [ ] Credential evidence cannot be fetched through a public media URL; unauthorized downloads are rejected and audited.
- [ ] Medical responses are not cached across users and clinical details/secrets are absent from logs.
- [ ] Protected reads, downloads, verification decisions, clinical mutations, and grant changes produce appropriate audit events.

Use DRF integration tests for the permission matrix, transaction tests against PostgreSQL for dispensing, and a small browser end-to-end suite for patient → doctor → pharmacy. Run frontend type checking/lint/build and backend deployment checks. Test business outcomes and unauthorized access paths, not just individual helper functions.

## 16. Build instruction for a developer or coding agent

> Build MedyLink Lite according to this document. Use a single Next.js/React/TypeScript/Tailwind frontend and a Django REST Framework/PostgreSQL backend, retaining SimpleJWT, QR, and PDF tooling from the reference stack with supported dependencies. Deliver real authentication, provider verification, patient health cards, explicit patient sharing, longitudinal clinical records, prescriptions, and verified-pharmacy dispensing. Exclude ML/AI and the other features listed as out of scope. Follow the permission matrix and acceptance criteria. Complete the work in the listed phases, using real API/database integration rather than mock authentication or browser-only records. Provide source code, migrations, dependency locks, environment templates, tests, Docker development setup, and production/backup instructions. Document any implementation decision that changes this specification; do not silently widen data access or add excluded features.

**Definition of done:** A patient can register and obtain a health card; independently verified doctors can contribute to the same patient history after approval; independently verified pharmacies can dispense approved prescriptions against one consistent balance; and the authentication, privacy boundaries, persistence, and recovery procedures are verified.
