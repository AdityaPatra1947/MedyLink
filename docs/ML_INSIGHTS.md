# ML insights: run guide and viva notes

The ML work is an administrator-only extension. Existing patient and doctor
dashboards, authentication, provider approval, and clinical access rules are
unchanged. The current implementation operates on the explicitly synthetic
demonstration dataset and current clinical records in that environment.

## Open the application

From the project directory:

```powershell
npm run synthetic:manage -- migrate --noinput
npm run dev:synthetic
```

Open `http://localhost:3001/admin/ml` and use an existing synthetic administrator
account. Patient, doctor and pharmacist accounts cannot use the ML APIs. The
normal application database remains separate; this is not permission to merge
real patient records into the synthetic demonstration.

## Date and population filters

- **All history** means no start/end restriction. It is not limited to a project
  deadline or a fixed calendar week.
- A custom range selects clinical measurements using their dates; condition,
  railway-line and station-area filters narrow the cohort.
- Filtered summaries, measurement groups, geographic groups and aggregate model
  estimates reflect that selection. The model comparison retains the data window
  and evaluation of its saved training run.
- **Retrain with new data** creates a new comparison using the selected data. A
  narrow window may not contain enough consecutive visits or both outcomes.
- Viewing an old range is a **retrospective view with the saved model**, not an
  out-of-time backtest. The model may have been trained with later records.
- A disease filter selects the earlier visit. Its target is still the next
  actual visit, even if that visit records a different condition.

The application reads the current clinical tables, including supported extracted
reports, instead of relying solely on the original imported analytics snapshot.
It does not edit those records. Structured report data is used only when present;
there is no generic OCR or free-text medical understanding.

## Training from the terminal

Read coverage without training or creating an ML run:

```powershell
node scripts/synthetic.mjs manage run_ml_training --dry-run
```

Train all eligible history synchronously:

```powershell
node scripts/synthetic.mjs manage run_ml_training --sync
```

Train a selected range:

```powershell
node scripts/synthetic.mjs manage run_ml_training --sync --date-from 2025-01-01 --date-to 2026-10-03
```

Additional optional filters are `--disease-code`, `--line`, and `--station-id`.
`--admin-email` selects an existing active verified administrator as the recorded
actor. The web button performs the equivalent operation in a local background
worker. It reports queued/running/completed/failed/insufficient states and prevents
duplicate simultaneous training for the same dataset. Failed or insufficient
runs preserve the previous completed model. An interrupted local worker can be
retried after its stale-job timeout.

Artifacts are private under `.local/ml/<database identity>/<run UUID>/`, or the
operator-supplied `ML_ARTIFACT_ROOT`. A run contains `model_bundle.joblib` and
`evaluation.json`; raw clinical records are not exported there. Never load a
joblib/pickle file from an untrusted upload. Only server-created run paths are
used by the API.

## What is predicted

The binary target is whether the **immediately next recorded consultation** has
systolic BP at least 140 mmHg or diastolic BP at least 90 mmHg. It is a recorded
measurement category, not a diagnosis of hypertension and not a fixed 30-day
forecast. The interval between recorded visits varies.

Inputs use the earlier observation: age, systolic and diastolic readings, pulse,
temperature, BMI when available, glucose and its measurement context, recorded
condition count, available adherence observations, and recorded gender. Names, login
details, patient IDs and doctor identity do not enter the feature matrix.

The dataset preparation validates values, resolves linked corrections and report
duplicates, and respects measurement/availability dates. Missing or ambiguous
intervening readings are not skipped to find a more convenient future target.
The hand-coded patient health score is not used as a medical ground-truth label.

Historical adherence uses only immutable extracted-report observations that were
available by that visit. Mutable medicine logs have no version history, so they
are excluded from historical training. Current summaries can still use current
logs through the selected cutoff; a backfilled report cannot become an earlier
training input.

## Topics used

| Simple explanation | ML topic | Role in this project |
| --- | --- | --- |
| Combine earlier measurements into a two-category estimate | Logistic Regression | Interpretable classification baseline |
| Ask a sequence of learned questions | Decision Tree | Nonlinear, readable decision boundaries |
| Combine many randomized trees | Random Forest | Reduce sensitivity to a single tree |
| Add trees that improve earlier errors | Gradient Boosting | Sequential classification ensemble |
| Group similar health measurements | K-Means | Aggregate patient-profile groups |
| Find geographically concentrated observations | DBSCAN with haversine distance | Synthetic recorded-case groups |
| Display many measurements in two dimensions | PCA | Aggregate group-centre visualization only |
| Test on different patients | Grouped cross-validation and holdout evaluation | Avoid repeated-patient leakage |
| Measure correct flags, missed readings and overall results | Accuracy, precision, recall, F1, macro-F1, confusion matrix | Shared model comparison |
| Check which inputs affect measured performance | Permutation feature importance | Explain the selected model, without claiming causation |

Linear Regression, KNN, Naive Bayes and hierarchical clustering were not added
simply to increase the algorithm count. No SVM, NLP, neural network, association
rule or time-series forecasting feature was introduced.

## Evaluation and automatic selection

Four algorithms receive the same eligible examples, one fixed approximately 20%
patient-group holdout, and three shared grouped cross-validation folds in the
remaining data. All visits from one patient remain together. Each patient has
equal total evaluation weight so lengthy histories do not dominate. Model fitting
also balances the two outcome classes using weights computed only from each
training fold. This fixed policy addresses class imbalance without using test
labels to tune the model; baselines and evaluation weights are unchanged.

Median imputation, missingness indicators, scaling and category encoding are
fitted inside each training fold. The best method is chosen by mean validation
macro-F1, with positive-class recall breaking ties. Test results are recorded
after selection and are never used to choose a different algorithm.

Two baselines use the same examples: always predict the training majority class,
and carry forward the current BP category. Accuracy alone can be misleading
because below-threshold readings are much more common in this dataset.

- **Accuracy:** fraction of predictions that are correct.
- **Precision:** among elevated flags, the fraction that are truly elevated.
- **Recall:** among elevated outcomes, the fraction successfully flagged.
- **F1:** harmonic mean of precision and recall for elevated readings.
- **Macro-F1:** average F1 across both categories; the selection metric.
- **Confusion matrix:** rows are actual outcomes; columns are predictions.

Percentage metrics are patient-weighted. The confusion matrix reports raw
visit-pair counts and therefore need not reproduce the weighted percentages.
An F1 score is not presented as a clinical reliability percentage.

The fixed demonstration gate requires the selected model to exceed both
baselines by 0.01 macro-F1 in cross-validation and holdout, achieve holdout recall
of at least 0.50, and include at least ten independent holdout patients with
positive outcomes (and at least ten positive examples). A failed gate
keeps the comparison visible with **Not reliable enough for predictions**.
Passing this gate is not clinical validation.

## Privacy and limitations

The admin receives aggregate results, not individual patients, source notes or
private report files. Private pseudonymous keys are only for chronology and split
membership. Small groups are suppressed. Overlapping aggregate queries can still
permit inference; this is a synthetic demonstration, not a formal anonymization
system for real clinical deployment.

The existing data was generated by a simulation. Some measurements depend on
generated condition labels, while many next readings are independent draws. A
model can learn the generator rather than medicine, and may not beat the baseline.
There are no validated readmission, mortality or severity outcomes. Sparse and
irregular visits do not support claims of fixed-horizon clinical forecasting.

K-Means groups indicate similar standardized measurements. DBSCAN groups indicate
nearby recorded cases; they do not establish population incidence, transmission
or outbreaks. Feature importance describes model behaviour, not medical causes.

**Predictions support decisions and are not a diagnosis.**

## References

- [WHO: Hypertension](https://www.who.int/news-room/fact-sheets/detail/hypertension)
- [scikit-learn: Common pitfalls and data leakage](https://scikit-learn.org/stable/common_pitfalls.html)
- [scikit-learn: Grouped cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html)
- [scikit-learn: Clustering](https://scikit-learn.org/stable/modules/clustering.html)
- [scikit-learn: Permutation importance](https://scikit-learn.org/stable/modules/permutation_importance.html)

The PDF learning guide is generated from the completed evaluation, so its model
comparison contains measured results rather than example percentages.

## Measured demonstration result (3 October 2026)

The first completed version 1.0.1 run used 1,205 eligible consecutive-visit pairs
from 998 patients. The independent holdout contained 199 patients and 241 pairs.
Random Forest was selected by cross-validation macro-F1 (0.5205). Its holdout
accuracy was 69.85%, recall 35.71%, and macro-F1 0.5512. It did not pass the fixed
quality gate; the comparison and grouping remain available, with predictions
disabled. No algorithm was selected using its holdout score.

All 1,205 historical examples lack trustworthy earlier adherence observations;
the pipeline treats this as missing, not perfect adherence. Sixty later-uploaded
monthly reports contribute to current summaries but cannot be backfilled into
historical model inputs. Missing historical BP observations block 63 adjacent
pairs. Dates in the overview can extend beyond the eligible training period.

The aggregate reproducible evaluation is saved in `ml/reports/evaluation.json`.
Private fitted models stay in `.local/ml/`; they are not public downloads.
Rebuild the learning PDF with:

```powershell
.venv/Scripts/python.exe -m ml.build_guide
# To use a later completed run:
.venv/Scripts/python.exe -m ml.build_guide --report .local/ml/<database>/<run>/evaluation.json
```

## Files added or changed

- ML package: `ml/pipeline.py`, `ml/train.py`, `ml/test_pipeline.py`,
  `ml/__init__.py`, `ml/README.md`, `ml/build_guide.py`, `ml/reports/evaluation.json`.
- Backend additions: `backend/analytics/ml_dataset.py`, `ml_serializers.py`,
  `ml_services.py`, `ml_views.py`, `test_ml.py`,
  `management/commands/run_ml_training.py`, `migrations/0002_mlrun.py`.
- Backend integration: `backend/analytics/models.py` and `urls.py`.
- Frontend additions: `frontend/components/admin-ml.tsx`, `admin-ml.module.css`,
  `frontend/lib/ml-types.ts`, `frontend/tests/admin-ml.spec.ts`.
- Admin-only navigation integration: `frontend/components/app.tsx` and
  `admin-page.tsx`. `frontend/tests/role-scroll.spec.ts` includes the new sidebar
  entry in its expectation; existing section navigation is unchanged.
- Documentation: this guide and `output/pdf/MedyLink_ML_Explained.pdf`.

## Verification

- The full 191-test Django suite passed against isolated PostgreSQL. The SQLite
  run also passed, with nine database-specific tests skipped.
- Thirteen focused ML tests cover chronology barriers, patient-separated splits,
  training-only preprocessing/weights, baselines, suppression and quality gates.
- Desktop/mobile ML browser checks cover filters, role restrictions, retraining,
  failures, small groups and empty data. All 64 existing patient/provider/admin
  dashboard regression cases passed; five loading timeouts passed on retry with
  one browser worker and a longer time budget.
- Live synthetic checks completed background training, verified direct/pooled
  model persistence, all-history/custom/empty/condition filtering, CSRF denial,
  non-admin denial, and responsive rendering without JavaScript errors.
- The seven-page PDF was rendered and visually checked page by page. Database
  and file fingerprints confirm existing user/clinical data and protected
  patient/doctor/authentication files were preserved.
