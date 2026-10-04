# ML insights run guide and viva notes

The administrator ML workspace contains **disease prediction**, similar-measurement
groups and geographic groups. The blood-pressure prediction task and its training
have been removed. Clinical BP readings, patient trend charts, health-score
calculations and BP inputs to the disease task remain available.

## Open the application

For a new checkout, first complete the [fresh 4,000-patient import](../README.md#fresh-4000-patient-demo).
The repository contains both the original 1,000 patients and the published
3,000-patient expansion; model bundles are generated locally and are not in Git.

From the repository root, with the dedicated synthetic environment configured:

```powershell
npm run synthetic:manage -- migrate --noinput
npm run dev:synthetic
```

Open `http://localhost:3001/admin/ml` using an active, verified administrator.

This is the first section after admin sign-in. Scroll down for doctor approvals, pharmacist approvals, audit, and account security, or use the sidebar. Each section has a direct URL (for example, `/admin/doctors`); back, forward, and refresh restore that section. The previous `/admin/analytics` page now opens ML insights.
Other roles cannot use the ML APIs. The normal application database remains
separate. The feature is restricted to explicitly synthetic datasets.

## What disease prediction does

The system learns from visits with a known primary disease and estimates one of
ten conditions from visit-time measurements and symptom flags. The conditions
are Dengue, Influenza, Hypertension, Type 2 diabetes, Asthma, Anemia,
Gastroenteritis, Hypothyroidism, Osteoarthritis and Malaria.

Inputs are age, gender, station, month, temperature, BP, blood sugar, hemoglobin,
oxygen saturation, pulse, platelets and eight symptoms. Diagnosis text,
prescriptions, clinician identity and information entered after the visit are
excluded from the feature matrix. The known primary disease is the training
answer, never an input. This predicts a category at a visit, not a future BP
reading or a fixed-time disease forecast.

## Filters and counts

- **All history** uses every eligible recorded date, not a deadline or a fixed week.
- Search partial condition names, select several conditions and apply filters.
  Conditions combine with OR; dates, railway line and station also apply.
- Counts, charts, station-condition cells, groups and aggregate predictions use
  the selected cohort. Clear conditions followed by Apply restores all diseases.
- A recorded-diagnosis filter selects the patients/visits to examine. The model
  may estimate a different disease for those records. Prediction counts are not
  additional confirmed diagnoses.
- Saved model scores, per-disease test recall and feature bars belong to the saved
  training run. Changing exploration filters does not recalculate these scores.
- Historical views use the saved model and are not out-of-time backtests.
- Counts from one to four are hidden. Empty or insufficient groups are shown
  without invented values.

The snapshot service reads current consultations, labs and supported extracted
reports with their dates and availability checks. General medical OCR and
free-text understanding are not implemented.

## Train from the terminal or dashboard

```powershell
# Inspect coverage without creating a run.
npm run synthetic:manage -- run_ml_training --dry-run

# Compare and save the four disease models using all eligible history.
npm run synthetic:manage -- run_ml_training --sync

# Optional selected date range.
npm run synthetic:manage -- run_ml_training --sync --date-from 2025-01-01 --date-to 2026-09-30
```

Disease is the default and only supported task; `--task disease` is optional.
The **Retrain disease models** button applies the same filters in the local
background worker. A narrow selection may lack enough patients from all ten
diseases; insufficient or failed runs preserve the previous completed model.
Training does not change clinical records.

Artifacts stay private under `.local/ml/<database identity>/<run UUID>/` or
`ML_ARTIFACT_ROOT`. Each completed run contains an aggregate evaluation and its
model bundle. Only trusted, server-created joblib artifacts may be loaded.
Legacy BP run records remain audit history, but BP task requests are rejected,
legacy run detail is unavailable and queued legacy runs cannot execute.

## Topics used

| Plain explanation | ML topic | Use |
| --- | --- | --- |
| Find a simple scoring pattern | Logistic Regression | Disease classifier |
| Ask learned yes/no questions | Decision Tree | Disease classifier |
| Combine many trees | Random Forest | Disease classifier |
| Compare the most similar past examples | KNN | Disease classifier |
| Group similar measurements | K-Means | Aggregate patient-profile groups |
| Group nearby recorded cases | DBSCAN using haversine distance | Geographic concentrations |
| Display many measurements on two axes | PCA | Aggregate group-centre chart |
| Test using different patients | Stratified patient-level holdout and cross-validation | Avoid repeated-patient leakage |
| Measure correct and missed disease categories | Accuracy, macro-F1, recall and confusion matrix | Fair comparison |
| Shuffle one input and measure the score drop | Permutation importance | Explain model dependence |

Gradient Boosting was used only by the removed BP task and is no longer trained.
There is no added Linear Regression, Naive Bayes, hierarchical clustering, NLP,
neural-network, association-rule or time-series forecasting feature. Monthly
charts summarize recorded data; the health score and adherence are calculations.

## Evaluation and selected model

Each patient belongs to either the 80% development set or the 20% final test set.
Five shared stratified CV folds inside development compare the four algorithms.
Preprocessing is fitted within each fold. Patient weighting prevents long
histories dominating evaluation. Choose the highest CV macro-F1, then inspect
the held-out result; do not choose the winner using final-test accuracy.

The [saved disease report](../ml/reports/disease_evaluation.json) from 4 October
2026 used **3,892 patients and 10,997 visits**: 3,113 development patients and 779
test patients, with no patient overlap. Random Forest was selected, with **79.2%
test accuracy and 77.7% macro-F1**. Both demonstration thresholds passed: at least
75% accuracy and 70% macro-F1. This is measured synthetic performance, not a
clinical reliability percentage.

That saved result comes from the existing demonstration database. Published
fixtures reproduce a generated baseline and exclude later uploads or manual
edits, so fresh imports retrain their own model and may produce different
coverage and scores.

Accuracy is the share of correct categories. Recall for a disease measures how
many actual cases the model found. Macro-F1 balances precision and recall across
all ten disease categories. Confusion-matrix cells count raw visits, whereas
reported percentages use equal total patient weights.

Feature-importance points measure the decline in test macro-F1 after shuffling
one input. For example, an 11.13-point blood-sugar drop indicates reliance by this
saved model. It is not a diabetes probability or proof of causation.

## Grouping, privacy and limitations

The **Explore Mumbai** section uses an interactive Leaflet/OpenStreetMap map of
the existing 34 public Mumbai-area station anchors. Select a station to inspect
its filtered patient count and recorded conditions, or switch to nearby groups
to explore the existing DBSCAN aggregates. Station colors identify rail corridors;
they are not disease severity labels. Group and station lists provide the same
information below the map, including when the background map cannot load.

Only public station anchors and already-suppressed aggregate group locations
are plotted. Map images load from `https://tile.openstreetmap.org` with visible
OpenStreetMap attribution and normal browser caching; internet access is needed
for the background tiles. Tile requests contain map coordinates, not patient
records, condition counts or authentication tokens. The map uses no geocoding
service or API key, and does not change training or the underlying database.

K-Means describes similar standardized measurements; PCA displays aggregate
group centres. DBSCAN finds concentrated simulated cases, not transmission or
outbreaks. No private patient list, report text or individual coordinates are
returned. Small-count suppression does not guarantee anonymity under overlapping
queries. This release is limited to synthetic data.

The generator plants seasonality, symptom and measurement patterns with noise
and missing values. A model can learn generator assumptions rather than medicine.
External clinical validation, calibration and governed real data are future work.
The local training executor is not a durable production job queue.

**Predictions support decisions and are not a diagnosis.**

## Source and verification

- [Disease setup, generator and evaluation](../ml/DISEASE_TASK.md)
- [Package contracts and offline commands](../ml/README.md)
- Disease pipeline: `ml/disease_pipeline.py`; aggregate grouping: `ml/pipeline.py`
- Backend: `backend/analytics/ml_dataset.py`, `ml_services.py`, `ml_views.py`
- Frontend: `frontend/components/admin-ml.tsx`, `admin-disease.tsx`

```powershell
.venv/Scripts/python.exe -B -m unittest ml.test_pipeline ml.test_disease_pipeline ml.test_train -v
npm run test:backend -- analytics
npm run check
npm --prefix frontend run test:e2e -- tests/admin-ml.spec.ts
```
