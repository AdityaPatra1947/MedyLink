"""Patient-separated disease classification for authorized synthetic snapshots.

This additive experiment does not read Django models or modify the existing BP
task. The caller owns authorization, snapshot provenance and private storage.
Only features explicitly listed below enter the model; patient keys are used
only to keep every visit from one person in the same partition.
"""

from __future__ import annotations

import copy
import json
import math
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits

VERSION = "1.0.0"
DEFAULT_SEED = 42
DISPLAY_MINIMUM = 5
CV_FOLDS = 5
MIN_CLASS_PATIENTS = 8
DISEASE_LABELS = {
    "DENGUE": "Dengue", "INFLUENZA": "Influenza",
    "HYPERTENSION": "Hypertension", "TYPE2_DIABETES": "Type 2 diabetes",
    "ASTHMA": "Asthma", "ANEMIA": "Anemia",
    "GASTROENTERITIS": "Gastroenteritis", "HYPOTHYROIDISM": "Hypothyroidism",
    "OSTEOARTHRITIS": "Osteoarthritis", "MALARIA": "Malaria",
}
CLASSES = tuple(DISEASE_LABELS)
SYMPTOM_FEATURES = (
    "fever", "cough", "joint_pain", "vomiting", "fatigue", "breathlessness",
    "headache", "rash",
)
NUMERIC_FEATURES = (
    "age", "month", "temperature", "systolic", "diastolic", "glucose",
    "hemoglobin", "spo2", "pulse", "platelets",
) + SYMPTOM_FEATURES
CATEGORICAL_FEATURES = ("gender", "station_id")
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
FEATURE_LABELS = {
    "age": "Age", "month": "Visit month", "temperature": "Temperature",
    "systolic": "Upper blood pressure reading", "diastolic": "Lower blood pressure reading",
    "glucose": "Blood sugar", "hemoglobin": "Hemoglobin", "spo2": "Blood oxygen level",
    "pulse": "Heart rate", "platelets": "Platelet count", "gender": "Recorded gender",
    "station_id": "Station area", "fever": "Fever", "cough": "Cough",
    "joint_pain": "Joint pain", "vomiting": "Vomiting", "fatigue": "Fatigue",
    "breathlessness": "Breathlessness", "headache": "Headache", "rash": "Rash",
}
RANGES = {
    "age": (0, 120), "temperature": (30, 45), "systolic": (50, 300),
    "diastolic": (30, 200), "glucose": (20, 700), "hemoglobin": (2, 25),
    "spo2": (40, 100), "pulse": (20, 250), "platelets": (1000, 1500000),
}
TARGET = {
    "id": "primary_disease", "label": "Primary recorded disease",
    "definition": "Classify one of ten primary diseases using information available at the visit.",
    "disclaimer": "Based on simulated data, not real patients. Predictions support decisions and are not a diagnosis.",
}
LIMITATIONS = [
    "These are simulated patients and labels; test scores do not establish clinical accuracy.",
    "The model chooses one primary disease from ten known classes and cannot detect an unlisted disease.",
    "Patients may have more than one disease, but this task predicts only the primary label for each visit.",
    "All visits from one patient stay in one partition. Metrics give each patient equal total weight; models fit the same visit rows.",
    "Splits are stratified using each patient's most frequent disease label; ties use disease-code order. This label is used only for splitting.",
    "This is a patient-separated retrospective comparison, not an evaluation on future dates or new station areas.",
    "Only measurements available at the visit enter training; missing data are imputed using training-fold statistics.",
    "Location and season reflect simulated patterns and can change in a real population.",
    "Feature importance explains model behavior, not medical causes or treatment advice.",
    "Counts of one to four are hidden. This display safeguard is not formal anonymization across repeated queries.",
]


def _stamp(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _number(value, minimum, maximum):
    if isinstance(value, bool):
        return np.nan
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError):
        return np.nan
    return value if math.isfinite(value) and minimum <= value <= maximum else np.nan


def _symptom(value):
    if isinstance(value, bool):
        return float(value)
    result = _number(value, 0, 1)
    return result if result in (0, 1) else np.nan


def _features(row, observed):
    """Ignore every field outside the allowlist, including diagnosis and text."""
    result = []
    for name in NUMERIC_FEATURES:
        if name == "month":
            # Derive season from the visit, never from a later edit/upload date.
            result.append(float(observed.month))
        elif name in SYMPTOM_FEATURES:
            result.append(_symptom(row.get(name)))
        else:
            result.append(_number(row.get(name), *RANGES[name]))
    gender = str(row.get("gender") or "").lower()
    result.append(gender if gender in {"male", "female", "other", "prefer_not_to_say"} else np.nan)
    station = row.get("station_id")
    result.append(str(station) if station is not None and str(station).strip() else np.nan)
    return result


def _snapshots(rows, *, require_label):
    prepared, excluded = [], Counter()
    now = datetime.now(timezone.utc)
    for row in rows:
        if not isinstance(row, dict) or not row.get("patient_key"):
            excluded["missing_patient_key"] += 1
            continue
        if row.get("synthetic") is not True:
            excluded["not_explicitly_synthetic"] += 1
            continue
        observed, available = _stamp(row.get("observed_at")), _stamp(row.get("available_at"))
        if observed is None or available is None:
            excluded["invalid_or_missing_dates"] += 1
            continue
        if observed > now:
            excluded["future_visit"] += 1
            continue
        if available > observed:
            excluded["available_after_visit"] += 1
            continue
        label = row.get("primary_disease")
        if require_label and (not isinstance(label, str) or label not in DISEASE_LABELS):
            excluded["missing_or_unknown_primary_disease"] += 1
            continue
        prepared.append((str(row["patient_key"]), observed, label, _features(row, observed)))
    # Ambiguous rows at the same visit time are not silently selected or counted twice.
    duplicates = Counter((key, stamp) for key, stamp, _, _ in prepared)
    result = [item for item in prepared if duplicates[item[:2]] == 1]
    excluded["ambiguous_same_visit_rows"] += len(prepared) - len(result)
    result.sort(key=lambda item: (item[0], item[1]))
    return result, {key: value for key, value in excluded.items() if value}


def _dominant_labels(y, groups):
    """One stable stratification label per patient, never a model input."""
    grouped = defaultdict(Counter)
    for label, patient in zip(y, groups):
        grouped[str(patient)][str(label)] += 1
    patients = np.asarray(sorted(grouped), dtype=object)
    labels = np.asarray([min(grouped[key], key=lambda label: (-grouped[key][label], label)) for key in patients], dtype=object)
    return patients, labels


def prepare_examples(rows):
    """Return internal feature/target/group arrays and aggregate coverage."""
    rows = list(rows)
    snapshots, excluded = _snapshots(rows, require_label=True)
    x = np.asarray([item[3] for item in snapshots], dtype=object).reshape((-1, len(FEATURES)))
    y = np.asarray([item[2] for item in snapshots], dtype=object)
    groups = np.asarray([item[0] for item in snapshots], dtype=object)
    _, dominant = _dominant_labels(y, groups)
    counts = Counter(y)
    dominant_counts = Counter(dominant)
    per_class_patients = {code: len(set(groups[y == code])) for code in CLASSES}
    patients_with_labels = defaultdict(set)
    for group, label in zip(groups, y):
        patients_with_labels[group].add(label)
    data = {
        "input_rows": len(rows), "eligible_rows": len(y), "eligible_patients": len(set(groups)),
        "class_counts": {code: counts[code] for code in CLASSES},
        "patients_per_class": per_class_patients,
        "dominant_class_patients": {code: dominant_counts[code] for code in CLASSES},
        "patients_with_multiple_primary_labels": sum(len(labels) > 1 for labels in patients_with_labels.values()),
        "excluded_rows": excluded,
        "missing_feature_counts": {name: sum(isinstance(value, (float, np.floating)) and np.isnan(value) for value in x[:, position]) for position, name in enumerate(FEATURES)},
        "date_from": min((item[1] for item in snapshots), default=None),
        "date_to": max((item[1] for item in snapshots), default=None),
    }
    for key in ("date_from", "date_to"):
        data[key] = data[key].isoformat() if data[key] else None
    return x, y, groups, data


def make_splits(y, groups, seed=DEFAULT_SEED):
    """Stratify patients, then expand each partition to all their visit rows."""
    y, groups = np.asarray(y, dtype=object), np.asarray(groups, dtype=object)
    if len(y) != len(groups):
        raise ValueError("Every example must have one patient key.")
    patients, strata = _dominant_labels(y, groups)
    counts = Counter(strata)
    if any(counts[code] < MIN_CLASS_PATIENTS for code in CLASSES):
        raise ValueError("Need at least eight independent patients for each of the ten primary diseases before an 80/20 split and five-fold comparison.")
    training_patients, test_patients = train_test_split(
        np.arange(len(patients)), test_size=0.20, random_state=seed, stratify=strata,
    )
    training_patients = np.sort(training_patients)
    test_patients = np.sort(test_patients)
    if min(Counter(strata[training_patients]).values()) < CV_FOLDS:
        raise ValueError("Each disease needs at least five training patients for five-fold patient-stratified comparison.")
    training = np.flatnonzero(np.isin(groups, patients[training_patients]))
    holdout = np.flatnonzero(np.isin(groups, patients[test_patients]))
    folds = []
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=seed)
    for train_index, validation_index in cv.split(training_patients, strata[training_patients]):
        fit = np.flatnonzero(np.isin(groups, patients[training_patients[train_index]]))
        validate = np.flatnonzero(np.isin(groups, patients[training_patients[validation_index]]))
        folds.append((fit, validate))
    return training, holdout, folds


def patient_weights(groups):
    counts = Counter(groups)
    return np.asarray([1.0 / counts[group] for group in groups], dtype=float)


def _models(seed):
    # These choices are fixed before seeing holdout results; no holdout tuning.
    return [
        ("logistic_regression", "Logistic Regression", LogisticRegression(C=1.0, max_iter=1500, class_weight="balanced", random_state=seed)),
        ("decision_tree", "Decision Tree", DecisionTreeClassifier(max_depth=10, min_samples_leaf=5, class_weight="balanced", random_state=seed)),
        ("random_forest", "Random Forest", RandomForestClassifier(n_estimators=140, max_depth=16, min_samples_leaf=2, class_weight="balanced_subsample", n_jobs=1, random_state=seed)),
        ("knn", "KNN", KNeighborsClassifier(n_neighbors=11, weights="distance", n_jobs=1)),
    ]


def _fit(estimator, x, y):
    numeric = Pipeline([
        ("missing", SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True)),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("missing", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
        ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    preprocess = ColumnTransformer([
        ("numeric", numeric, list(range(len(NUMERIC_FEATURES)))),
        ("categorical", categorical, list(range(len(NUMERIC_FEATURES), len(FEATURES)))),
    ], sparse_threshold=0)
    model = Pipeline([("preprocess", preprocess), ("model", clone(estimator))])
    return model.fit(x, y)


def metrics(y, predicted, groups):
    weights = patient_weights(groups)
    recall = recall_score(y, predicted, labels=list(CLASSES), average=None, zero_division=0, sample_weight=weights)
    return {
        "accuracy": float(accuracy_score(y, predicted, sample_weight=weights)),
        "macro_f1": float(f1_score(y, predicted, labels=list(CLASSES), average="macro", zero_division=0, sample_weight=weights)),
        "per_disease_recall": {code: float(recall[index]) for index, code in enumerate(CLASSES)},
        "per_disease_counts": {code: int((y == code).sum()) for code in CLASSES},
        "per_disease_patients": {code: len(set(groups[y == code])) for code in CLASSES},
        "confusion_matrix": confusion_matrix(y, predicted, labels=list(CLASSES)).astype(int).tolist(),
        "confusion_labels": list(CLASSES), "examples": len(y), "patients": len(set(groups)),
    }


def _cv_summary(folds):
    return {
        "mean": {key: float(np.mean([fold[key] for fold in folds])) for key in ("accuracy", "macro_f1")},
        "std": {key: float(np.std([fold[key] for fold in folds])) for key in ("accuracy", "macro_f1")},
        "folds": folds,
    }


def choose_by_cv(models):
    """Keep selection independent of every final-test metric."""
    return max(models, key=lambda item: item["cv"]["mean"]["macro_f1"])


def prediction_gate(holdout):
    checks = {"holdout_macro_f1_at_least_0_70": holdout["macro_f1"] >= 0.70,
              "holdout_accuracy_at_least_0_75": holdout["accuracy"] >= 0.75}
    reasons = []
    if not checks["holdout_macro_f1_at_least_0_70"]:
        reasons.append(f"balanced disease score {holdout['macro_f1']:.1%} is below 70%")
    if not checks["holdout_accuracy_at_least_0_75"]:
        reasons.append(f"correct results {holdout['accuracy']:.1%} is below 75%")
    return checks, ("Simulation checks passed; these results are not clinical validation." if not reasons
                    else "Predictions are disabled: " + "; ".join(reasons) + ".")


def _importance(pipeline, x, y, groups, seed):
    with threadpool_limits(limits=1):
        result = permutation_importance(
            pipeline, x, y, scoring="f1_macro", n_repeats=3,
            random_state=seed, sample_weight=patient_weights(groups), n_jobs=1,
        )
    return sorted([
        {"feature": key, "label": FEATURE_LABELS[key], "importance": float(result.importances_mean[index]),
         "standard_deviation": float(result.importances_std[index])}
        for index, key in enumerate(FEATURES)
    ], key=lambda item: -item["importance"])


def _safe_count(value):
    return None if 0 < value < DISPLAY_MINIMUM else int(value)


def _safe_counts(values):
    return {key: _safe_count(value) for key, value in values.items()}


def _public_report(report):
    result = copy.deepcopy(report)
    data = result["data"]
    for key in ("input_rows", "eligible_rows", "eligible_patients", "patients_with_multiple_primary_labels"):
        data[key] = _safe_count(data[key])
    for key in ("class_counts", "patients_per_class", "dominant_class_patients", "excluded_rows", "missing_feature_counts"):
        data[key] = _safe_counts(data[key])
    data["small_count_rule"] = "Counts from one to four are hidden individually (null); zero means no records."
    if result.get("split"):
        for key in ("training_patients", "holdout_patients", "training_examples", "holdout_examples"):
            result["split"][key] = _safe_count(result["split"][key])
    for model in result["models"]:
        for item in model["cv"]["folds"] + [model["holdout"]]:
            for code in CLASSES:
                if item["per_disease_patients"][code] < DISPLAY_MINIMUM:
                    item["per_disease_recall"][code] = None
            item["per_disease_counts"] = _safe_counts(item["per_disease_counts"])
            item["per_disease_patients"] = _safe_counts(item["per_disease_patients"])
            item["confusion_matrix"] = [[_safe_count(cell) for cell in row] for row in item["confusion_matrix"]]
            item["confusion_matrix_suppressed"] = any(cell is None for row in item["confusion_matrix"] for cell in row)
            for key in ("examples", "patients"):
                item[key] = _safe_count(item[key])
    return result


def _save(directory, report, pipelines=None, selected=None):
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / "model_bundle.joblib"
    if pipelines is not None:
        joblib.dump({"version": VERSION, "task": "disease", "selected": selected,
                     "pipelines": pipelines, "report": report}, model_path)
    elif model_path.exists():
        # A failed/insufficient rerun must never leave an older enabled model.
        model_path.unlink()
    (directory / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


def train_and_evaluate(rows, output_dir, seed=DEFAULT_SEED):
    """Compare four fixed classifiers on shared patient-separated partitions."""
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** 32:
        raise ValueError("Seed must be an integer between zero and 2**32 - 1.")
    x, y, groups, data = prepare_examples(rows)
    report = {
        "version": VERSION, "task": "disease", "status": "insufficient_data", "target": TARGET,
        "seed": seed, "created_at": datetime.now(timezone.utc).isoformat(),
        "versions": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "numpy": np.__version__},
        "data": data, "labels": list(CLASSES),
        "class_labels": [{"code": code, "label": DISEASE_LABELS[code]} for code in CLASSES],
        "features": [{"key": key, "label": FEATURE_LABELS[key]} for key in FEATURES],
        "models": [], "selection": None, "split": None, "feature_importance": [],
        "training_dates": {"from": data["date_from"], "through": data["date_to"]},
        "limitations": LIMITATIONS,
    }
    directory = Path(output_dir)
    try:
        training, holdout, folds = make_splits(y, groups, seed)
    except ValueError as error:
        report["reason"] = str(error)
        public = _public_report(report)
        _save(directory, public)
        return public
    report["split"] = {
        "method": "Stratified 80/20 split of patients, then five shared stratified patient folds on the training patients.",
        "training_patients": len(set(groups[training])), "holdout_patients": len(set(groups[holdout])),
        "training_examples": len(training), "holdout_examples": len(holdout),
        "folds": CV_FOLDS, "patient_overlap": 0,
        "stratification": "Patient's most frequent primary disease; tied labels sort by disease code. Every visit stays with its patient.",
        "selection_rule": "Highest mean five-fold cross-validation macro F1; fixed model order breaks exact ties.",
        "holdout_policy": "Evaluate the final test set after selection. Do not change algorithms or parameters using these results.",
        "metric_weighting": "Equal total weight per patient, shared by all algorithms. Confusion matrices contain raw visit counts.",
    }
    pipelines = {}
    with threadpool_limits(limits=1):
        for key, name, estimator in _models(seed):
            comparisons = []
            for fit, validate in folds:
                pipeline = _fit(estimator, x[fit], y[fit])
                comparisons.append(metrics(y[validate], pipeline.predict(x[validate]), groups[validate]))
            report["models"].append({"id": key, "name": name, "cv": _cv_summary(comparisons)})
            pipelines[key] = _fit(estimator, x[training], y[training])
        # Selection is frozen before any holdout prediction is requested.
        selected = choose_by_cv(report["models"])
        for item in report["models"]:
            item["holdout"] = metrics(y[holdout], pipelines[item["id"]].predict(x[holdout]), groups[holdout])
    checks, message = prediction_gate(selected["holdout"])
    report.update({
        "status": "completed", "selection": {
            "model_id": selected["id"], "model_name": selected["name"], "name": selected["name"],
            "prediction_enabled": all(checks.values()), "message": message, "gate_checks": checks,
            "criterion": "Highest mean five-fold patient-stratified cross-validation macro F1.",
            "gate_policy": "Fixed before evaluation: final-test macro F1 >= 0.70 and accuracy >= 0.75. Passing is not clinical validation.",
        },
        "feature_importance": _importance(pipelines[selected["id"]], x[holdout], y[holdout], groups[holdout], seed),
        "feature_importance_method": "Three permutation repeats on final-test data after selection; change in patient-weighted macro F1. No feature selection or tuning uses these results.",
    })
    public = _public_report(report)
    _save(directory, public, pipelines, selected["id"])
    return public


def predict_summary(rows, output_dir):
    """Aggregate one latest selected visit per patient; never return identities."""
    directory = Path(output_dir)
    report = json.loads((directory / "evaluation.json").read_text(encoding="utf-8"))
    if report.get("task") != "disease" or report.get("version") != VERSION:
        raise ValueError("The saved disease model version is unsupported; retrain it.")
    snapshots, excluded = _snapshots(list(rows), require_label=False)
    latest = {}
    for item in snapshots:
        latest[item[0]] = item
    enabled = bool((report.get("selection") or {}).get("prediction_enabled"))
    base = {
        "task": "disease", "prediction_enabled": enabled,
        "eligible_patients": _safe_count(len(latest)), "excluded_rows": _safe_counts(excluded),
        "counts": [], "class_labels": report["class_labels"], "labels": list(CLASSES),
        "as_of": max((item[1] for item in latest.values()), default=None),
        "training_through": report["training_dates"]["through"],
        "interpretation": "Retrospective simulated cohort estimates from each patient's latest selected visit; not live diagnoses.",
        "disclaimer": TARGET["disclaimer"],
    }
    base["as_of"] = base["as_of"].isoformat() if base["as_of"] else None
    if not enabled:
        return {**base, "reason": (report.get("selection") or {}).get("message") or report.get("reason")}
    if len(latest) < DISPLAY_MINIMUM:
        return {**base, "reason": "At least five patients are required for an aggregate result."}
    # Only server-created private bundles may be loaded; joblib is executable.
    bundle = joblib.load(directory / "model_bundle.joblib")
    if bundle.get("task") != "disease" or bundle.get("version") != VERSION or not bundle["report"]["selection"]["prediction_enabled"]:
        raise ValueError("The saved disease model does not match an enabled training result.")
    x = np.asarray([item[3] for item in latest.values()], dtype=object)
    with threadpool_limits(limits=1):
        predicted = bundle["pipelines"][bundle["selected"]].predict(x)
    raw_counts = Counter(predicted)
    counts = [{"code": code, "label": DISEASE_LABELS[code], "count": _safe_count(raw_counts[code])} for code in CLASSES]
    suppressed = any(item["count"] is None for item in counts)
    return {**base, "counts": counts, "suppressed": suppressed,
            "reason": "Counts of one to four are hidden." if suppressed else None}
