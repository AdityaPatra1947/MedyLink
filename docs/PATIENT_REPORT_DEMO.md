# First-five patient report demo

After the synthetic dataset has been imported, this command adds reports for
the mapped patients `PAT0001` through `PAT0005`. Find their local logins in the
ignored `.local/synthetic/mumbai_stations_v1/credentials.json` file and sign in
at `http://localhost:3001`. Passwords and patient identities are preserved by
the report import. The regular environment is not seeded by this command.

| Patient | Monthly history | Latest BP | Latest fasting glucose |
| --- | ---: | --- | --- |
| Deepa Saha / PAT0001 | 12 months | 116/74 mmHg | 92 mg/dL |
| Pooja Singh / PAT0002 | 6 months | 132/84 mmHg | 108 mg/dL |
| Milind Shah / PAT0003 | 24 months | 146/92 mmHg | 156 mg/dL |
| Amrita Apte / PAT0004 | 12 months | 124/78 mmHg | 118 mg/dL |
| Dhruv Ansari / PAT0005 | 6 months | 138/86 mmHg | 136 mg/dL |

These are fictional snapshots ending 30 September 2026. Each month has an
original two-page PDF, consultation, detailed symptoms and assessment, linked
maintenance prescription, and attribution to one of the existing approved
synthetic doctors. Earlier records are retained. Every PDF is marked synthetic;
the prescriptions are examples, not treatment recommendations.

## Create or verify the fixture

From the repository root in PowerShell, with the existing synthetic `.env`:

```powershell
# Apply additive schema changes to the synthetic database.
node scripts/synthetic.mjs manage migrate --noinput

# Generate and validate 60 PDFs without database writes.
node scripts/synthetic.mjs manage enrich_demo_patients --as-of 2026-09-30

# Import the generated observations, visits and prescriptions.
node scripts/synthetic.mjs manage enrich_demo_patients --as-of 2026-09-30 --apply

# Run the app with the synthetic database.
npm run dev:synthetic
```

The command requires synthetic settings, a `synthetic_` database, the original
import mapping, the expected five test identities and existing approved
synthetic providers. Deterministic record IDs make reruns idempotent. It never
changes a password, email, patient profile or provider approval. File cleanup
and database writes are transactional. Generated previews and a manifest are in
`output/pdf/first-five-patients`; app uploads use authenticated private storage.

## What the numbers mean

**Adherence** is `100 × taken doses / scheduled doses` in the latest 30 calendar
days, rounded to one decimal for display. The source is the explicit daily dose
diary printed in each PDF, or a subsequently recorded patient dose log. Missing
days remain unknown; neither blood pressure, glucose nor pharmacy dispensing
proves that a medicine was taken. The popup shows the numerator, denominator,
dates and logged-day coverage.

**Demo health score** is an illustrative index, not a clinically validated
assessment, diagnosis, disease-risk model or treatment recommendation:

`round(0.30 × systolic points + 0.20 × diastolic points + 0.30 × fasting-glucose points + 0.20 × unrounded adherence percentage)`

The final score uses conventional half-up rounding. For this snapshot the five
scores are **99, 73, 51, 86 and 64**, with adherence **93.3%, 83.3%, 68.9%, 96.7%
and 85.6%**, respectively. These values are calculated from the stored readings
and dose counts; they are not fixed display constants.

| Component | Input ranges → points |
| --- | --- |
| Systolic, mmHg | <90 → 40; 90–119 → 100; 120–129 → 85; 130–139 → 70; 140–159 → 50; ≥160 → 25 |
| Diastolic, mmHg | <60 → 40; 60–79 → 100; 80–89 → 70; 90–99 → 50; ≥100 → 25 |
| Fasting glucose, mg/dL | <70 → 30; 70–99 → 100; 100–125 → 70; 126–179 → 40; ≥180 → 20 |
| Adherence | Actual unrounded percentage, from 0 to 100 |

The point bands and weights are custom demo choices. The score requires a
supported monthly report measured within 45 days and at least seven logged
dose days within 30 days. It becomes unavailable when those requirements are
not met. Both demo scoring and structured-report extraction are explicitly
enabled only in synthetic settings. The normal app retains its configurable
score-policy mechanism. Risk level is no longer displayed on patient dashboards.

BP and glucose trends use the **measurement date**, not the upload date, and
show up to 24 observations with their doctor and source report. Report counts,
consultation counts, active prescriptions and download counts come from stored
records and actual activity. Glucose reference flags use the report's 70–99
mg/dL range; BP remains a vital measurement, not a laboratory analyte. An
abnormal flag is not an automated diagnosis.

## Extraction and report access

The doctor upload handler and demo importer use the same bounded PDF parser.
It checks patient and uploading-doctor account IDs, units, timestamp, clinical
value bounds, unique fields, dates and daily dose counts. Extraction creates
report-linked measurements and dose observations within the report's database
transaction. Reprocessing an already extracted report does not duplicate rows.

This is a deterministic importer for the documented MedyLink monthly PDF
format, not general-purpose medical OCR. Arbitrary scanned or third-party PDFs
remain available to view/download without guessed measurements. A malformed
supported-format report is rejected rather than partially imported.

View opens the authenticated inline PDF endpoint; Download uses attachment
disposition. Both enforce existing patient/provider access checks. Viewing is
audited separately and does not increase the download count.

## Report-format references

The original layout includes patient identity, doctor attribution, collection
and report dates, specimen/accession, method, result, unit, reference range,
clinical context and follow-up. It does not reproduce an external laboratory's
branding, signatures or accreditation.

- [American Heart Association: My Blood Pressure Log](https://professional.heart.org/-/media/Files/Health-Topics/High-Blood-Pressure/My-Blood-Pressure-Log.pdf): repeated cuff readings and recording date/time.
- [Labcorp: glucose test and sample report](https://www.labcorp.com/tests/001032/glucose): specimen and enzymatic method, fasting preparation and 70–99 mg/dL reference interval.
- [Labcorp glucose sample PDF](https://files.labcorp.com/testmenu-d8/sample_reports/001032.pdf): patient, physician, specimen and result fields.
- [NIDDK: diabetes and prediabetes tests](https://www.niddk.nih.gov/health-information/professionals/clinical-tools-patient-management/diabetes/diabetes-prediabetes): interpretation requires clinical context and confirmatory testing where appropriate.

Medication examples were checked against [NHS amlodipine information](https://www.nhs.uk/medicines/amlodipine/) and [NHS metformin information](https://www.nhs.uk/medicines/metformin/). These references inform plausible fictional records; they do not validate the demo score.
