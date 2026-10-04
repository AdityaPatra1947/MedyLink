# Patient dashboard health data

The dashboard uses database observations. New tables begin empty; no health score, risk band, adherence percentage, abnormal laboratory count, or regional alert is fabricated. Existing consultation vitals continue to populate blood pressure and glucose trends. This release does not parse uploaded PDFs into laboratory values or infer medication-taking from pharmacy dispensing.

## Using the dashboard

Open **Overview** after signing in as a patient. All patient sections share one scrolling page; use the sidebar to jump between them. Counts and identity cards are summaries, while health score, risk, adherence, laboratory, and vital controls open their detail dialogs. Select chart points with a mouse or keyboard to inspect their date and source, or expand the readings table. **Recent notifications** links to the related section. See [dashboard navigation](DASHBOARD_NAVIGATION.md).

- **Adherence:** open the adherence summary, enter scheduled and taken doses, and save. The percentage recalculates from your own saved logs.
- **Abnormal lab values:** open the lab results dialog and add a numerical result using the unit and optional reference limits printed on the report. The dashboard refreshes its latest-result summary.
- **Blood pressure / blood sugar:** charts read consultation vitals entered by the doctor. Missing readings stay empty. Corrections replace a chart reading while retaining its original consultation date.
- **Health score / risk:** the calculation engine waits for a configured method and all required fresh observations. Adding observations alone will not enable an unconfigured score.
- **Regional alerts:** a source adapter must be connected before notices can be displayed.

## Adherence

`GET /api/v1/patients/me/adherence/` returns the signed-in verified patient's daily logs for today and the preceding 29 UTC dates. `PUT` accepts JSON:

```json
{"date":"2026-09-29","scheduled_doses":3,"taken_doses":2}
```

Numbers must be JSON integers; booleans, fractions, and numeric strings are rejected. Scheduled doses must be 1–10,000; taken doses must be 0–scheduled doses. Future and older dates are rejected. PUT creates or replaces only that patient's entry for the specified date; changes are audited. The database enforces one entry per patient/date and valid dose bounds.

Both methods return `{ "results": [{ "id", "date", "scheduled_doses", "taken_doses" }], "summary": ... }`. The summary is null with no logs; otherwise its keys are `percentage`, `scheduled_doses`, `taken_doses`, `days_logged`, and `period_days` (30). Percentage is `100 * sum(taken) / sum(scheduled)`, rounded to one decimal. Days not logged are unknown, not missed doses. This is patient-reported adherence, not independently verified ingestion. Only patients can use these endpoints.

## Laboratory observations

`GET/POST /api/v1/patients/me/labs/` is for the signed-in patient. `GET/POST /api/v1/patients/<patient UUID>/labs/` requires a currently approved doctor. Pharmacists and administrators cannot access these clinical endpoints. POST accepts:

```json
{
  "name": "Analyte name as printed on the report",
  "value": 4.25,
  "unit": "unit printed on the report",
  "reference_low": null,
  "reference_high": null,
  "measured_at": "2026-09-29T08:00:00Z",
  "report_id": null
}
```

The optional report must belong to the same patient. Name and unit are required, values use fixed precision decimals, lower reference limits cannot exceed upper limits, and future measurements are rejected. The service records the actual authenticated author and role; clients cannot supply those fields. Observations are append-only through the API. Every read and append is audited.

Returned result fields: `id`, `name`, `value`, `unit`, `reference_low`, `reference_high`, `flag`, `measured_at`, `recorded_by_name`, `source` (patient/doctor), `report_id`. `flag` is `low` or `high` only against the supplied reference bounds; it is `normal` within the bounds that were supplied, and `unknown` if neither bound was supplied. A missing bound is not invented. Flags are comparisons, not diagnoses.

GET returns paginated `{results, next, summary:{abnormal,total}}`. The summary uses the latest result per trimmed, case-insensitive analyte name and trimmed **case-sensitive** unit. Different units are never converted or combined. `total` counts these latest results, including those without references. `abnormal` counts latest results flagged high/low; it is null if every latest result lacks references. Both are null without results. Summary counts cover all observations rather than only the displayed page.

## Versioned health score policy

`HEALTH_SCORE_POLICY` defaults to None. Configure the environment variable `HEALTH_SCORE_POLICY_JSON` only after the responsible clinical owner has supplied and validated a calculation method, weights, required inputs, freshness windows, and risk-band labels. The engine does not ship a clinical formula or claim a generic 0–100 metric is medically valid.

The following is an exact **synthetic arithmetic example for development**, not a recommended clinical policy. Its labels and thresholds must be replaced by an owner-reviewed method before use:

```json
{
  "method": "OWNER_DEFINED_METHOD",
  "version": "REVIEWED_VERSION",
  "label": "OWNER_DEFINED_SCORE_LABEL",
  "components": [
    {
      "key": "adherence",
      "label": "OWNER_DEFINED_COMPONENT_LABEL",
      "weight": 1,
      "max_age_days": 7,
      "min_days_logged": 7,
      "rules": [
        {"upper_bound": 50, "score": 20},
        {"upper_bound": null, "score": 80}
      ]
    }
  ],
  "risk_bands": [
    {"min_score": 0, "label": "OWNER_DEFINED_BAND_A"},
    {"min_score": 70, "label": "OWNER_DEFINED_BAND_B"}
  ]
}
```

Supported component keys: `systolic`, `diastolic`, `blood_sugar`, `adherence`, `abnormal_labs`, `conditions`. Each requires a unique key, label, positive finite weight, `max_age_days` (1–3650), and ordered rules with strictly increasing finite upper bounds followed by a final null bound. Rule scores must be finite 0–100. Rules are inclusive (`value <= upper_bound`); final null is the catch-all. The final score is the rounded weighted mean of component scores. Risk bands require unique minimum scores in 0–100, including 0; the highest qualifying minimum supplies the returned risk label. `min_days_logged` is optional and valid only for adherence (1–30).

All configured inputs must be present and fresh. Vitals use the newest parsed consultation observation; adherence uses the newest logged date plus any configured minimum logged-day count. Laboratory scoring requires supplied reference bounds for every latest tracked test and freshness of every latest result. Condition scoring requires recorded condition evidence: each active condition must be recent; if all recorded conditions were resolved, the latest resolution must be recent. No condition history means unknown for this component, not proof of no conditions. No policy, malformed policy, missing input, or stale input returns `health_score: null`, `risk_level: null`, and an explanatory `health_score_reason`. Other measured dashboard facts remain available.

A calculated health score returns `{value,label,method,calculated_at,components:[{key,label,value,score,weight}]}`. Method includes the configured version. Risk level is a nullable string. The score and risk label have only the meaning assigned by the configured, clinically reviewed method.

## Regional alert adapter

`HEALTH_ALERTS_PROVIDER` defaults to an empty string. To connect a reviewed source, set it to an operator-controlled Python callable such as `project_health.alerts.for_patient`. It receives the Patient object and must return:

```json
{
  "available": true,
  "items": [{
    "id": "source-alert-id",
    "title": "Source announcement title",
    "description": "Source announcement text",
    "source_url": "https://public-health.example/notice",
    "published_at": "2026-09-29T08:00:00Z",
    "region": "Source region"
  }]
}
```

Implement region selection, source authorization, freshness checks, bounded network timeouts, and caching in this trusted adapter. The dashboard does not send patient information to an external service itself. The adapter is disabled by default. Its returned fields and HTTP(S) source URLs are validated; invalid results and exceptions yield `{available:false,items:[]}` with a generic log message containing no patient information. A successful empty source response means no source notices returned; an unavailable adapter never claims there is no outbreak.

## Migration and verification

Migration `clinic/0005_patient_health_tracking.py` adds the two tables and database constraints. Test with `python backend/manage.py test clinic.test_health_tracking --settings=config.test_settings`; this uses an isolated SQLite database by default. PostgreSQL validation should use a temporary Neon branch and a test database. Do not seed invented observations to make the score appear populated.
