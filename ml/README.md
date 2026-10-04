# MedyLink synthetic ML experiments

This package extends the existing Django analytics service. It never reads the
database, changes clinical records, or decides who may view them. The backend
must supply authorized synthetic snapshots and keep model artifacts private.
Predictions support discussion and are **not a diagnosis or a clinically
validated risk estimate**.

## Running it

The integrated admin page starts training through the backend's job route. The
server extracts the selected date/area cohort, records the dataset fingerprint,
and writes each run to its own private directory. Existing patients, doctors and
pharmacists keep their access rules.

For a technical exercise, export an authorized synthetic snapshot list using the
backend extraction service, keep it under ignored `.local/`, then run from the
repository root:

```powershell
.venv/Scripts/python.exe -m ml.train --input .local/ml/visits.json --output .local/ml/manual-run-001
.venv/Scripts/python.exe -B -m unittest ml.test_pipeline -v
```

The CLI does not connect to a database. It rejects an existing nonempty output
directory. `evaluation.json` contains aggregate results; `model_bundle.joblib`
contains the fitted pipelines and their report. No bundle is created when the
data is insufficient. Never serve either path as an unrestricted static file.
Only load joblib files created by this application: loading an untrusted pickle
or joblib file can execute code. The installed backend requirements already
include scikit-learn, NumPy, joblib and threadpoolctl.

## What the models do

The target is whether the **next recorded visit** has systolic BP at least
140 mmHg or diastolic BP at least 90 mmHg. This is a measurement threshold, not a
hypertension diagnosis. Visits occur at varying intervals, so the system does
not call this a 30-day risk forecast.

| Model | Plain-English explanation | Why compare it? |
| --- | --- | --- |
| Logistic regression | Combines measurements using a simple weighted rule learned from examples. | An interpretable linear baseline. |
| Decision tree | Learns a short sequence of measurement-based questions. | Can capture thresholds and simple interactions. |
| Random forest | Combines many varied decision trees. | Tests whether averaging trees improves stability. |
| Gradient boosting | Adds small trees that correct earlier errors. | Tests a different way to combine nonlinear rules. |

The comparison also includes two simple alternatives: always choose the most
common outcome in training, and repeat the patient's current BP category. A
complicated model is not automatically better than these baselines.

## Reproducible comparison

- The four algorithms use the **same frozen patient groups and folds**. About
  20% of patients are held out. All visits from a patient stay in one split.
- The remaining patients use three grouped cross-validation folds. Imputation,
  missingness indicators, scaling and categorical encoding are fitted within
  each training fold. Model settings and the random seed are fixed in code.
- Training begins with equal total weight per patient, then balances total
  positive/negative weight using only that training fold's labels. This fixed
  policy handles the uncommon elevated-reading outcome for all four models.
  Evaluation keeps patient weights and does not rebalance outcome classes.
- Choose the model with highest mean validation **macro F1**; positive-class
  recall breaks ties. The held-out results do not choose the winner.
- After selection, show held-out accuracy, precision, recall, positive-class
  F1, macro F1 and the confusion matrix for all models and both baselines.
  Metrics use patient weights; the confusion matrix contains raw visit-pair
  counts and is labelled accordingly.
- Shuffling one held-out feature five times measures its contribution to the
  selected model. This explanation is computed **after selection** and never
  used to refit or select the model. Zero/negative contribution is displayed
  honestly. Correlated measurements share information; importance is not cause.

Accuracy can look impressive when elevated readings are uncommon. Macro F1
gives both categories equal importance; recall shows how many elevated next
readings were found, while precision shows how many flagged readings were
actually elevated. None of these metrics is a calibrated probability that an
individual patient will become ill.

## Fixed demonstration gate

Predictions remain unavailable unless the selected model beats **both** simple
baselines by at least 0.01 macro F1 in validation and held-out evaluation, finds
at least half the held-out elevated readings, and has at least ten independent
patients with positive held-out outcomes. This gate was fixed before evaluation. It is an educational
check, not a clinical acceptance criterion. A failed gate still shows the
complete model comparison; the application must not invent reassuring scores.

Training requires at least 100 visit pairs, 50 patients and ten distinct
patients with each outcome. The current synthetic generator can produce weak
predictive signal, so poor results are a valid project finding.

## Similar-patient groups

K-Means groups the latest eligible observation per patient using standardized
numeric measurements. Missing numeric values use cohort medians only for
grouping. Public output includes group counts, average measurements and
aggregate centres; it does not include members or patient points. PCA provides
two summary axes for displaying those group centres, not a health score.
Groups describe similarity, not shared diagnoses or treatment needs. Existing
geographic DBSCAN remains a separate backend service.

## Backend input contract

Each list entry is an already validated historical snapshot:

```json
{
  "patient_key": "internal-pseudonymous-key",
  "observed_at": "2026-01-01T09:00:00Z",
  "available_at": "2026-01-01T09:00:00Z",
  "eligible_index": true,
  "age": 46,
  "gender": "female",
  "systolic": 132,
  "diastolic": 84,
  "pulse": 76,
  "temperature": 36.8,
  "bmi": 26.2,
  "glucose": 108,
  "glucose_context": "fasting",
  "condition_count": 1,
  "adherence": null,
  "disease_codes": ["HYPERTENSION"]
}
```

`patient_key` is used only for joins, ordering and grouping. Demographic names,
contact details, doctor identity, station, diagnosis text and condition codes
are not prediction features. Numeric prior condition count is allowed only
when known at that visit. Glucose context is explicit; random readings are
not silently treated as fasting values. Null numeric inputs stay missing until
fold-specific imputation. Missing/bad BP cannot define the target.

For disease filters, send the **complete chronological sequence** in the date
window and mark qualifying input rows with `eligible_index`. Build adjacent
pairs first, then filter the index visit; the next visit can have a different
diagnosis. Missing BP, ambiguous timestamps and retrospectively backfilled rows
remain barriers, so the algorithm cannot jump past an intervening visit and
mislabel a later one as the next visit. Both visits must be inside the selected
date window. The backend must ensure prior lab/condition/adherence fields were
known at the input observation, and must not substitute later corrections.

`train_and_evaluate(history_rows, private_run_dir)` returns the public report.
`predict_summary(current_rows, private_run_dir)` uses the selected model only
when its gate passed and returns aggregate counts. For historical views these
are explicitly retrospective synthetic estimates, not live forecasts.
`cluster_patient_groups(current_rows, n_groups=3)` returns aggregate K-Means
groups independently of predictive model quality.

Small counts of one to four are hidden, including confusion matrices with such
cells. This is a display safeguard, not a formal anonymization guarantee under
repeated overlapping queries. This release remains synthetic-only.

## Limitations for the viva

The dataset contains generated labels and simulated measurements, uneven visit
intervals, limited independent patients, incomplete fields and deliberately
planted geographic patterns. Correlations reflect generator assumptions.
Patient-group holdout tests generalization to unseen simulated patients; it
does not establish clinical validity, future temporal robustness or transfer
to a different hospital. Readmission/severity outcomes are not recorded, and
five longer patient histories do not justify population-level forecasting.
Future work needs independently governed datasets, a clinically reviewed target,
external and temporal validation, adequate subgroup coverage and calibration.
