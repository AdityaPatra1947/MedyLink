# MedyLink synthetic ML experiments

This package extends the administrator analytics service. It receives authorized,
explicitly synthetic snapshots from Django; it never queries the database or
changes clinical records or access rules. Predictions support decisions and are
**not a diagnosis or a clinically validated risk estimate**.

## Supported features

- **Disease prediction:** Logistic Regression, Decision Tree, Random Forest and
  KNN classify the primary disease recorded at a visit, among ten supported diseases.
- **Similar measurement groups:** K-Means describes aggregate patient profiles.
- **Group-centre chart:** PCA projects aggregate K-Means centres into two dimensions.
- **Geographic groups:** the backend's DBSCAN service groups nearby simulated cases.

Future blood-pressure prediction and its training are removed. BP remains an
ordinary clinical measurement and an input to disease classification/grouping.
Historical BP run rows and private artifacts are retained only as inert history;
the API and command line cannot train, serve or activate them.

## Run disease training

With the synthetic environment configured and its base dataset imported:

```powershell
npm run synthetic:manage -- run_ml_training --dry-run
npm run synthetic:manage -- run_ml_training --sync
```

The administrator's **Retrain disease models** button uses the same task.
`--task disease` is optional; disease is the only accepted task. A failed or
insufficient run preserves the previous completed disease model.

For an offline exercise, export an authorized snapshot list under ignored
`.local/`, then run from the repository root:

```powershell
.venv/Scripts/python.exe -m ml.train --input .local/ml/visits.json --output .local/ml/manual-run-001
.venv/Scripts/python.exe -B -m unittest ml.test_pipeline ml.test_disease_pipeline ml.test_train -v
```

The CLI rejects an existing nonempty output directory. Private run directories
contain `evaluation.json` and, after successful training, `model_bundle.joblib`.
Never serve these as unrestricted static files or load joblib/pickle files from
untrusted sources. The backend requirements provide scikit-learn, NumPy, joblib
and threadpoolctl.

## Reproducible comparison

All four classifiers use the same stratified 80/20 **patient-level** split and
five cross-validation folds within training. Every visit from a patient stays
in the same partition. Imputation, scaling and encoding are fitted inside each
training fold. Evaluation weights each patient equally even with repeat visits.

Select the highest mean CV macro-F1, then evaluate on the held-out patients.
Report accuracy, macro-F1, per-disease recall and a raw-visit confusion matrix.
The final test does not choose the winner. Aggregate predictions require test
macro-F1 of at least 0.70 and accuracy of at least 0.75. This simulation gate is
not clinical approval.

Features include age, gender, station, month, vitals, blood tests and eight
symptom flags. Inputs recorded after the visit are excluded. Diagnosis text,
medications, names, IDs and doctor identities are not predictors. Primary disease
is the target, never an input. See [the disease task guide](DISEASE_TASK.md)
for field names, missingness, minimum counts, filtering and the saved evaluation.

## Public module contracts

- `ml.disease_pipeline.train_and_evaluate(rows, private_run_dir)` trains and
  reports the disease comparison. The package-level `ml.train_and_evaluate`
  export also points to this disease task.
- `ml.disease_pipeline.predict_summary(rows, private_run_dir)` returns aggregate
  disease counts when the saved model passes its gate; `ml.predict_summary`
  exposes the same function.
- `ml.pipeline.cluster_patient_groups(rows, n_groups=3)` returns K-Means/PCA
  aggregates independently of disease model training.

K-Means uses the latest eligible observation per patient and cohort-median
imputation for numeric grouping. Output contains counts, average measurements and
centres, never individual members or patient points. PCA axes are not a health
score. Missing locations are excluded from geographic grouping rather than guessed.

## Interpretation and limitations

Condition filters select recorded diagnoses; the saved disease model may estimate
other labels within that cohort. Saved comparison scores and feature importance
retain their training selection until retraining. An old date range viewed with a
saved model is a retrospective display, not an out-of-time backtest.

Counts of one to four are hidden, including small confusion-matrix cells. This
is a display safeguard, not formal anonymization under overlapping queries.
Generator assumptions and simulated labels limit generalization. Patient-level
holdout does not establish medical accuracy, future robustness or suitability
for another hospital. Independently governed data and clinical validation remain
future work.
