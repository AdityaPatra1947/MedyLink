# Disease prediction experiment

This additive task lives in `ml/disease_pipeline.py`. It leaves the existing
next-visit blood-pressure task in `ml/pipeline.py` unchanged. Inputs must be
authorized, explicitly synthetic snapshots; the module never queries a database.

## Run in the existing demo

From the repository root, the wrapper loads the existing private synthetic
configuration without changing your normal database or printing credentials:

```powershell
npm run synthetic:manage -- migrate --noinput
npm run synthetic:manage -- generate_synthetic_data --count 3000 --seed 42
npm run synthetic:manage -- run_ml_training --task disease --dry-run
npm run synthetic:manage -- run_ml_training --task disease --sync
npm run dev:synthetic
```

The equivalent Django commands, from `backend/` **with the dedicated synthetic
environment configured** (`DJANGO_SETTINGS_MODULE=config.synthetic_settings`
and `SYNTHETIC_DATABASE_URL` set), are:

```sh
python manage.py generate_synthetic_data --count 3000 --seed 42
python manage.py run_ml_training --task disease --sync
```

Open `http://localhost:3001/admin/ml`. The Disease prediction card compares four
methods, displays the saved development/test patient counts and explains the
top five feature contributions with bars. Green means the simulation gate
passed; amber means more evidence is needed; red means a training attempt
failed. These colors never establish clinical safety.

Use Conditions to search partial names, select several diseases, and Apply
filters. Selected diseases are combined with OR; station/line/date filters also
apply. Clear conditions restores all diseases after Apply. Counts, charts,
groups and station-condition cells use the same selection. The saved model's
comparison and importance keep their original training selection until another
training run. A narrow selection without all ten classes cannot train a complete
ten-disease model; that failed/insufficient run preserves the previous model.

The existing BP task and its models remain under **Blood pressure prediction
and training**. `--task blood_pressure` is still the default command behavior.
Both tasks share MLRun storage but have independent active models.

## Verified demonstration: 4 October 2026

Seed 42 appended **3,000 patients, 8,987 visits and 25,596 lab results**, taking
the mapped population to **4,000 patients across 34 stations**. Repeating the
command added zero records. Fingerprints verified that all original accounts
and clinical rows were unchanged.

The saved [aggregate evaluation](reports/disease_evaluation.json) used **10,997
eligible visits from 3,892 patients**: 3,113 for training/CV and 779 for the final
test, with zero patient overlap. It excluded 258 input observations without a
supported, unambiguous primary label. Some original patients therefore do not
contribute to this classification task.

| Method | CV macro F1 | Final accuracy | Final macro F1 |
| --- | ---: | ---: | ---: |
| Logistic Regression | 74.6% | 76.8% | 74.8% |
| Decision Tree | 66.7% | 66.7% | 67.8% |
| **Random Forest** | **77.9%** | **79.2%** | **77.7%** |
| KNN | 72.8% | 74.5% | 72.9% |

Random Forest passed both fixed demonstration thresholds. No parameters were
changed using these test results. These values describe simulated records,
not performance on real patients. Model bundles remain private in the existing
database-scoped `.local/ml/` run directory.

## Synthetic generator

The command appends to the configured Mumbai dataset, reusing its 34 station
areas and approved doctors. It creates 2–4 visits per patient between 31 October
2024 and 30 September 2026. Ten unequal class weights, seasonal/geographic
patterns, overlapping symptoms, approximately 5% independent label noise,
approximately 5% missing measurement/symptom cells and approximately 15%
secondary disease histories make this a learnable but imperfect exercise.

`--count` is the total generated population for that seed. Repeating the same
seed/count is a no-op; increasing count appends the deterministic remaining
patients. Existing accounts, records and original import manifests are not
rewritten. Generated accounts are inactive with unusable passwords. Patient
area provenance, visit metadata and an audit event mark the data as synthetic.
Additional observation rows update live analytics coverage and invalidate stale
clustering caches. Counts of 1–4 stay hidden; zero remains a real zero.

Legacy visits join disease training only when the recorded diagnosis names one
unambiguous supported primary disease. New visits store an explicit primary
label separately from the allowed measurements. Diagnosis text, medication,
secondary disease codes, generator metadata and patient/doctor identifiers are
never classifier features. Historical corrections and later-uploaded reports
cannot supply information that was unknown at the visit.

## Checks

```powershell
node scripts/manage.mjs test analytics --settings=config.test_settings --noinput
.venv/Scripts/python.exe -B -m unittest ml.test_pipeline ml.test_disease_pipeline -v
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

The existing browser suite includes disease selection, clearing, suppressed
counts, separate-task retraining, quality gates and mobile layouts.

The ML insights read endpoint has its own uncached proxy with a 120-second
deadline. This avoids the general rewrite proxy's 30-second cutoff when the
database is slow. Session cookies, permission checks and filter parameters are
preserved. Other API endpoints keep their existing timeout. Lab coverage is
counted in the database; only glucose results needed by the fallback are loaded
in detail, while Hb/platelets already stored in visit measurements are retained.

Run the proxy regression checks (including a real response delayed beyond 30
seconds) from the repository root:

```powershell
$env:RUN_ML_PROXY_SLOW_TEST = 'true'
node --test frontend/server-tests/ml-insights-proxy.test.mjs
Remove-Item Env:RUN_ML_PROXY_SLOW_TEST
```

## What the four algorithms do

| Algorithm | Plain explanation | Why it is included |
| --- | --- | --- |
| Logistic Regression | Finds simple patterns, like a scoring checklist. | A linear classification baseline that combines several measurements. |
| Decision Tree | Asks yes/no questions step by step. | Captures thresholds and interactions in one tree. |
| Random Forest | Many decision trees voting together. | Reduces the instability of an individual tree. |
| KNN | Looks at the most similar past patients. | Compares a distance-based method with learned coefficients and trees. |

The target is the **primary disease at the visit**, one of ten configured labels.
It is not a forecast of future disease, a diagnosis, or a treatment recommendation.
Secondary diseases can overlap, but this is a single-label classification task.

## Evaluation rules

- Split **patients**, not visits: 80% for development and 20% for final testing.
  A patient's most frequent primary label supplies the stratification category;
  ties sort by disease code. All visits stay with that patient.
- Run five stratified patient folds inside the development set. Every model sees
  the same folds and holdout patients. At least eight independent patients are
  needed in each of the ten stratification categories.
- Each pipeline fits its missing-value imputer, numeric scaler and categorical
  encoder on its training rows only. Unknown station categories are ignored by
  the encoder instead of failing at prediction time.
- Select the highest **mean cross-validation macro F1**. Model order breaks exact
  ties. Hyperparameters are fixed in code before final testing.
- Evaluate all four on the reserved patients. Enable the chosen model only when
  final-test macro F1 is at least 0.70 **and** accuracy is at least 0.75. Do not
  switch to a different model based on its holdout results.
- Accuracy is the fraction of correct results. Recall asks how many visits with
  each disease were correctly identified. F1 balances precision and recall;
  macro F1 gives each disease equal importance. Metrics give each patient equal
  total weight across their visits. Confusion matrices contain raw visit counts.
- Permutation importance shuffles an input and measures the drop in final-test
  macro F1. It is calculated after selection for explanation only, never tuning.

## Inputs and temporal boundaries

The allowlist includes age, gender, station, visit month, temperature, systolic and
diastolic BP, glucose, hemoglobin, SpO2, pulse, platelets, and eight symptom flags.
Visit month is derived from the observation timestamp. Numeric units are °C,
mmHg, mg/dL glucose, g/dL hemoglobin, percent SpO2, beats/minute pulse and
platelets/µL (for example 150000). Missing symptoms are unknown, not false.

Names, contact details, patient IDs, diagnosis text, medications and other fields
cannot enter the feature matrix. Patient keys are used privately for grouping.
Rows with missing dates, non-synthetic provenance, future visits or data recorded
after the visit are excluded. Ambiguous simultaneous rows are excluded together.
The backend remains responsible for constructing truthful historical snapshots.

## Artifacts and limitations

`train_and_evaluate(rows, output_dir, seed=42)` writes `evaluation.json` and a
private `model_bundle.joblib`. Insufficient data produces only the report and
removes a stale model in that directory. `predict_summary(rows, output_dir)` uses
one latest eligible visit per patient and returns only aggregate disease counts.
The prediction API always supplies a `counts` array of `{code, label, count}`
objects; it is empty when results are unavailable. `class_labels` and `labels`
identify the ten diseases even when the prediction gate is closed.
Counts of one to four are hidden individually, including confusion-matrix cells.

Keep bundles private and load only application-created files: joblib can execute
code, and KNN retains anonymous feature examples internally. Passing the gate on
simulated records is not clinical validation. The evaluation does not measure
generalization to later dates, unseen areas, real patients or unlisted diseases.

Run the isolated tests from the repository root:

```powershell
.venv/Scripts/python.exe -B -m unittest ml.test_disease_pipeline -v
```

## Files added or changed

New generator and tests:

- `backend/analytics/synthetic_generation.py`
- `backend/analytics/management/commands/generate_synthetic_data.py`
- `backend/analytics/test_synthetic_generation.py`

New disease learning module, tests and documentation:

- `ml/disease_pipeline.py`
- `ml/test_disease_pipeline.py`
- `ml/DISEASE_TASK.md`
- `ml/reports/disease_evaluation.json`

Existing backend integration extended:

- `backend/analytics/models.py`
- `backend/analytics/migrations/0004_mlrun_task.py` (new)
- `backend/analytics/ml_dataset.py`
- `backend/analytics/ml_serializers.py`
- `backend/analytics/ml_services.py`
- `backend/analytics/ml_views.py`
- `backend/analytics/management/commands/run_ml_training.py`
- `backend/analytics/services.py`
- `backend/analytics/views.py`
- `backend/analytics/test_disease_ml.py` (new)
- `backend/analytics/test_live_metadata.py` (new)
- `backend/analytics/test_ml_query_scope.py` (new)

Admin UI, styles and checks:

- `frontend/components/admin-disease.tsx` (new)
- `frontend/components/admin-disease.module.css` (new)
- `frontend/components/admin-disease-filter.tsx` (new)
- `frontend/components/admin-ml.tsx`
- `frontend/components/admin-ml.module.css`
- `frontend/lib/ml-types.ts`
- `frontend/tests/admin-ml.spec.ts`
- `frontend/app/api/v1/admin/analytics/ml/insights/route.ts` (new)
- `frontend/lib/server/ml-insights-proxy.mjs` (new)
- `frontend/server-tests/ml-insights-proxy.test.mjs` (new)
- `README.md`
- `docs/ML_INSIGHTS.md`

Patient and doctor dashboards and the existing blood-pressure learning module
were not rewritten.
