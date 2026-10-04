"""Small reproducible experiments, isolated from Django and clinical permissions.

Only server-validated synthetic snapshots may be supplied here. Patient keys are
used for chronology/group splitting and never enter feature matrices or public
reports. The calling service owns authorization, filtering, and private paths.
"""

from __future__ import annotations

import json
import math
import platform
import copy
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    silhouette_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits

VERSION = "1.0.1"
DEFAULT_SEED = 20261003
MIN_PAIRS = 100
MIN_PATIENTS = 50
MIN_CLASS_PATIENTS = 10
DISPLAY_MINIMUM = 5
NUMERIC_FEATURES = (
    "age", "systolic", "diastolic", "pulse", "temperature", "bmi", "glucose",
    "condition_count", "adherence",
)
CATEGORICAL_FEATURES = ("gender", "glucose_context")
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
LABELS = {
    "age": "Age", "systolic": "Upper blood pressure reading",
    "diastolic": "Lower blood pressure reading", "pulse": "Pulse",
    "temperature": "Temperature", "bmi": "Body mass index",
    "glucose": "Blood sugar reading", "condition_count": "Recorded conditions",
    "adherence": "Recorded medicine-taking", "gender": "Recorded gender",
    "glucose_context": "Blood sugar test type",
}
TARGET = {
    "id": "next_recorded_visit_elevated_bp",
    "label": "Elevated blood pressure at the next recorded visit",
    "definition": "Next recorded systolic >= 140 mmHg or diastolic >= 90 mmHg.",
    "positive_label": "Elevated reading",
    "negative_label": "Below this reading threshold",
    "horizon": "Next recorded visit; the interval varies by patient.",
    "disclaimer": "Synthetic research only. Predictions support discussion and are not a diagnosis or a clinically validated risk estimate.",
}
LIMITATIONS = [
    "All results describe an artificial dataset; they do not establish clinical accuracy.",
    "The target is a future recorded measurement, not a diagnosis of hypertension.",
    "The next visit can be days or months later; this is not a fixed-horizon prediction.",
    "Repeat visits from one patient stay in one split. Evaluation gives each patient equal total weight; training additionally balances outcome classes within each fold.",
    "Missing observations are not normal results; preprocessing is fitted inside each training fold.",
    "Generated measurements may not contain useful predictive signal; simple baselines can win.",
    "Model scores and feature importance do not establish medical causes or treatment advice.",
    "Counts of one to four are hidden. This display safeguard is not a formal anonymization guarantee across repeated queries.",
]


def _number(value, low=None, high=None):
    if isinstance(value, bool):
        return np.nan
    try:
        result = float(value)
    except (TypeError, ValueError):
        return np.nan
    if not math.isfinite(result) or (low is not None and result < low) or (high is not None and result > high):
        return np.nan
    return result


def _stamp(value):
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _features(row):
    bmi = _number(row.get("bmi"), 8, 100)
    if np.isnan(bmi):
        height = _number(row.get("height_cm"), 80, 250)
        weight = _number(row.get("weight_kg"), 15, 400)
        if not np.isnan(height) and not np.isnan(weight):
            bmi = _number(weight / (height / 100) ** 2, 8, 100)
    gender = str(row.get("gender") or "unknown").lower()
    if gender not in {"male", "female", "other", "prefer_not_to_say"}:
        gender = "unknown"
    context = str(row.get("glucose_context") or "unknown").lower()
    if context not in {"fasting", "random", "postprandial", "post_meal"}:
        context = "unknown"
    return [
        _number(row.get("age"), 0, 120),
        _number(row.get("systolic"), 50, 300),
        _number(row.get("diastolic"), 30, 200),
        _number(row.get("pulse", row.get("heart_rate_bpm")), 20, 250),
        _number(row.get("temperature", row.get("temperature_c")), 30, 45),
        bmi, _number(row.get("glucose", row.get("glucose_mg_dl")), 20, 700),
        _number(row.get("condition_count"), 0, 1000),
        _number(row.get("adherence"), 0, 100), gender, context,
    ]


def _valid_bp(values):
    return not np.isnan(values[1]) and not np.isnan(values[2]) and values[1] > values[2]


def _snapshots(rows, *, historical):
    patients = defaultdict(list)
    excluded = Counter()
    for row in rows:
        if not isinstance(row, dict) or not row.get("patient_key"):
            excluded["missing_patient_key"] += 1
            continue
        observed = _stamp(row.get("observed_at", row.get("measured_at")))
        if observed is None:
            excluded["invalid_date"] += 1
            continue
        available = _stamp(row.get("available_at")) or observed
        if historical and available > observed:
            excluded["backfilled_after_measurement"] += 1
        features = _features(row)
        if not _valid_bp(features):
            excluded["missing_or_invalid_bp"] += 1
            if not historical:
                continue
        patients[str(row["patient_key"])].append((observed, features, row))
    result = {}
    for key, visits in patients.items():
        visits.sort(key=lambda value: value[0])
        # Keep an invalid barrier at ambiguous dates rather than jumping across a visit.
        dates = Counter(value[0] for value in visits)
        result[key] = []
        ambiguous_seen = set()
        for visit in visits:
            if dates[visit[0]] == 1:
                result[key].append(visit)
            elif historical and visit[0] not in ambiguous_seen:
                result[key].append((visit[0], [np.nan] * len(FEATURES), visit[2]))
                ambiguous_seen.add(visit[0])
        excluded["ambiguous_simultaneous_rows"] += sum(count for count in dates.values() if count > 1)
    return result, dict(excluded)


def prepare_pairs(rows):
    """Return internal arrays and anonymous coverage; no model fitting or I/O."""
    snapshots, excluded = _snapshots(rows, historical=True)
    values, outcomes, groups, gaps, index_dates, target_dates = [], [], [], [], [], []
    skipped_pairs = Counter()
    for patient, visits in sorted(snapshots.items()):
        for first, second in zip(visits, visits[1:]):
            if first[2].get("eligible_index", True) is not True:
                skipped_pairs["index_outside_selected_condition"] += 1
                continue
            if not _valid_bp(first[1]) or not _valid_bp(second[1]):
                skipped_pairs["missing_or_ambiguous_adjacent_bp"] += 1
                continue
            if any((_stamp(visit[2].get("available_at")) or visit[0]) > visit[0] for visit in (first, second)):
                skipped_pairs["backfilled_adjacent_observation"] += 1
                continue
            gap = (second[0] - first[0]).total_seconds() / 86400
            if gap <= 0:
                continue
            values.append(first[1])
            outcomes.append(int(second[1][1] >= 140 or second[1][2] >= 90))
            groups.append(patient)
            gaps.append(gap)
            index_dates.append(first[0])
            target_dates.append(second[0])
    x = np.asarray(values, dtype=object).reshape(-1, len(FEATURES))
    y = np.asarray(outcomes, dtype=int)
    group_array = np.asarray(groups, dtype=object)
    support = {str(label): len(set(group_array[y == label])) for label in (0, 1)}
    data = {
        "input_rows": len(rows), "eligible_pairs": len(y),
        "eligible_patients": len(set(groups)),
        "class_counts": {"below_threshold": int((y == 0).sum()), "elevated": int((y == 1).sum())},
        "patients_per_class": {"below_threshold": support["0"], "elevated": support["1"]},
        "excluded_rows": excluded,
        "excluded_pairs": dict(skipped_pairs),
        "patients_without_pairs": sum(len(visits) < 2 for visits in snapshots.values()),
        "interval_days": {"min": round(min(gaps), 2), "median": round(float(np.median(gaps)), 2), "max": round(max(gaps), 2)} if gaps else None,
        "missing_feature_counts": {name: int(sum(np.isnan(v) for v in x[:, index])) for index, name in enumerate(NUMERIC_FEATURES)},
        "date_from": min(index_dates).isoformat() if index_dates else None,
        "date_to": max(target_dates).isoformat() if target_dates else None,
    }
    return x, y, group_array, data


def patient_weights(groups):
    counts = Counter(groups)
    weights = np.asarray([1 / counts[group] for group in groups], dtype=float)
    return weights / weights.mean() if len(weights) else weights


def training_weights(y, groups):
    """Fixed class balance on training labels only; evaluation is not rebalanced."""
    weights = patient_weights(groups)
    total = float(weights.sum())
    for label in (0, 1):
        mask = y == label
        mass = float(weights[mask].sum())
        if mass:
            weights[mask] *= total / (2 * mass)
    return weights / weights.mean() if len(weights) else weights


def make_splits(y, groups, seed=DEFAULT_SEED):
    """A frozen unseen-patient holdout plus shared grouped development folds."""
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    train, holdout = next(outer.split(np.zeros(len(y)), y, groups))
    inner = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=seed + 1)
    folds = [(train[a], train[b]) for a, b in inner.split(np.zeros(len(train)), y[train], groups[train])]
    if set(y[train]) != {0, 1} or set(y[holdout]) != {0, 1} or any(set(y[a]) != {0, 1} or set(y[b]) != {0, 1} for a, b in folds):
        raise ValueError("The grouped split does not have both outcomes in every fold; more independent patients are needed.")
    return train, holdout, folds


def _preprocessor():
    numeric = Pipeline([
        ("missing", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    return ColumnTransformer([
        ("numeric", numeric, list(range(len(NUMERIC_FEATURES)))),
        ("category", OneHotEncoder(handle_unknown="ignore", sparse_output=False), list(range(len(NUMERIC_FEATURES), len(FEATURES)))),
    ])


def _models(seed):
    return [
        ("logistic_regression", "Logistic regression", LogisticRegression(C=1.0, max_iter=1000, random_state=seed)),
        ("decision_tree", "Decision tree", DecisionTreeClassifier(max_depth=5, min_samples_leaf=10, random_state=seed)),
        ("random_forest", "Random forest", RandomForestClassifier(n_estimators=100, max_depth=7, min_samples_leaf=5, n_jobs=1, random_state=seed)),
        ("gradient_boosting", "Gradient boosting", GradientBoostingClassifier(n_estimators=80, learning_rate=0.05, max_depth=2, min_samples_leaf=10, random_state=seed)),
    ]


def metrics(y, predicted, groups):
    weight = patient_weights(groups)
    result = {
        "accuracy": accuracy_score(y, predicted, sample_weight=weight),
        "precision": precision_score(y, predicted, sample_weight=weight, zero_division=0),
        "recall": recall_score(y, predicted, sample_weight=weight, zero_division=0),
        "f1": f1_score(y, predicted, sample_weight=weight, zero_division=0),
        "macro_f1": f1_score(y, predicted, average="macro", sample_weight=weight, zero_division=0),
    }
    return {
        **{key: round(float(value), 6) for key, value in result.items()},
        "confusion_matrix": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
        "confusion_matrix_labels": ["Below threshold", "Elevated reading"],
        "confusion_matrix_axes": "Rows are actual outcomes; columns are model outputs. Raw visit-pair counts.",
        "weighting": "Equal total weight per patient; confusion matrix shows unweighted visit-pair counts.",
        "examples": int(len(y)), "patients": int(len(set(groups))),
    }


def _cv_summary(fold_metrics):
    names = ("accuracy", "precision", "recall", "f1", "macro_f1")
    return {
        "mean": {key: round(float(np.mean([row[key] for row in fold_metrics])), 6) for key in names},
        "std": {key: round(float(np.std([row[key] for row in fold_metrics])), 6) for key in names},
        "folds": fold_metrics,
    }


def _fit(model, x, y, groups):
    pipeline = Pipeline([("preprocess", _preprocessor()), ("model", clone(model))])
    pipeline.fit(x, y, model__sample_weight=training_weights(y, groups))
    return pipeline


def _importance(pipeline, x, y, groups, seed):
    # Only an explanation after the selection is frozen. Never fed back into fitting.
    with threadpool_limits(limits=1):
        result = permutation_importance(
            pipeline, x, y, scoring="f1_macro", n_repeats=5,
            random_state=seed, sample_weight=patient_weights(groups), n_jobs=1,
        )
    values = [{"feature": key, "label": LABELS[key],
               "importance": round(float(result.importances_mean[index]), 6),
               "standard_deviation": round(float(result.importances_std[index]), 6)}
              for index, key in enumerate(FEATURES)]
    return sorted(values, key=lambda row: -row["importance"])


def _write_report(directory, report):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


def _safe_count(value):
    return None if 0 < value < DISPLAY_MINIMUM else int(value)


def _safe_counts(values):
    return {key: _safe_count(value) for key, value in values.items()}


def _public_report(report):
    """Small-cell display suppression; preserve raw arrays only inside training."""
    result = copy.deepcopy(report)
    data = result["data"]
    hidden = False
    for key in ("input_rows", "eligible_pairs", "eligible_patients", "patients_without_pairs"):
        data[key] = _safe_count(data[key])
        hidden = hidden or data[key] is None
    for key in ("class_counts", "patients_per_class", "excluded_rows", "excluded_pairs", "missing_feature_counts"):
        original = data[key]
        data[key] = _safe_counts(original)
        hidden = hidden or any(value is None for value in data[key].values())
        if key in {"class_counts", "patients_per_class"} and any(value is None for value in data[key].values()):
            # Do not reconstruct a hidden outcome from the other outcome plus total.
            data[key] = {name: None for name in data[key]}
    if hidden:
        data["input_rows"] = data["eligible_pairs"] = data["eligible_patients"] = None
    data["small_counts_suppressed"] = hidden
    if result.get("split"):
        for key in ("training_patients", "holdout_patients", "training_examples", "holdout_examples", "holdout_positive_examples", "holdout_positive_patients"):
            result["split"][key] = _safe_count(result["split"][key])
    for model in result["models"] + result["baselines"]:
        for metric_row in model["cv"]["folds"] + [model["holdout"]]:
            cells = metric_row["confusion_matrix"]
            if any(0 < cell < DISPLAY_MINIMUM for row in cells for cell in row):
                metric_row["confusion_matrix"] = None
                metric_row["confusion_matrix_suppressed"] = True
            metric_row["examples"] = _safe_count(metric_row["examples"])
            metric_row["patients"] = _safe_count(metric_row["patients"])
    return result


def train_and_evaluate(rows, artifact_dir, *, seed=DEFAULT_SEED):
    """Train four models on identical grouped splits; return no person-level data."""
    rows = list(rows)
    directory = Path(artifact_dir)
    x, y, groups, data = prepare_pairs(rows)
    report = {
        "version": VERSION, "status": "insufficient_data", "target": TARGET,
        "data": data, "seed": seed, "models": [], "baselines": [],
        "selection": None, "feature_importance": [], "limitations": LIMITATIONS,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "versions": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "numpy": np.__version__},
        "training_dates": {"from": data["date_from"], "through": data["date_to"]},
    }
    minority = min(data["patients_per_class"].values())
    if len(y) < MIN_PAIRS or len(set(groups)) < MIN_PATIENTS or minority < MIN_CLASS_PATIENTS:
        report["reason"] = "Need at least 100 eligible visit pairs, 50 independent patients and 10 patients with each outcome."
        public = _public_report(report)
        _write_report(directory, public)
        return public
    try:
        train, holdout, folds = make_splits(y, groups, seed)
    except ValueError as error:
        report["reason"] = str(error)
        public = _public_report(report)
        _write_report(directory, public)
        return public
    report["split"] = {
        "method": "Fixed 20% patient-group holdout and three shared patient-group cross-validation folds.",
        "training_patients": len(set(groups[train])), "holdout_patients": len(set(groups[holdout])),
        "training_examples": len(train), "holdout_examples": len(holdout),
        "holdout_positive_examples": int((y[holdout] == 1).sum()),
        "holdout_positive_patients": len(set(groups[holdout][y[holdout] == 1])),
        "folds": len(folds), "patient_overlap": 0,
        "selection_rule": "Highest mean cross-validation macro F1; recall breaks ties; model order breaks exact ties.",
        "holdout_policy": "The holdout is evaluated once after model selection and never used for model or parameter selection.",
        "fitting_weights": "First assign equal total weight to each training patient, then equalize positive and negative total weight using training-fold labels only. Evaluation retains patient weights without class rebalance.",
    }
    pipelines = {}
    with threadpool_limits(limits=1):
        # Complete every development comparison before accessing holdout labels.
        for key, name, estimator in _models(seed):
            comparisons = []
            for a, b in folds:
                fitted = _fit(estimator, x[a], y[a], groups[a])
                comparisons.append(metrics(y[b], fitted.predict(x[b]), groups[b]))
            report["models"].append({"id": key, "name": name, "cv": _cv_summary(comparisons)})
            pipelines[key] = _fit(estimator, x[train], y[train], groups[train])
        selected = max(report["models"], key=lambda item: (item["cv"]["mean"]["macro_f1"], item["cv"]["mean"]["recall"]))
        for item in report["models"]:
            item["holdout"] = metrics(y[holdout], pipelines[item["id"]].predict(x[holdout]), groups[holdout])
        # Baselines use the same folds/holdout and the same patient weights.
        for kind, label in (("majority", "Always choose the most common result"), ("carry_forward", "Repeat the current BP category")):
            def baseline(a, b):
                if kind == "carry_forward":
                    return np.asarray([int(row[1] >= 140 or row[2] >= 90) for row in x[b]])
                weight = patient_weights(groups[a])
                majority = int(float(np.average(y[a], weights=weight)) > 0.5)
                return np.full(len(b), majority, dtype=int)
            report["baselines"].append({"id": kind, "name": label,
                "cv": _cv_summary([metrics(y[b], baseline(a, b), groups[b]) for a, b in folds]),
                "holdout": metrics(y[holdout], baseline(train, holdout), groups[holdout])})
    best_baseline_cv = max(item["cv"]["mean"]["macro_f1"] for item in report["baselines"])
    best_baseline_test = max(item["holdout"]["macro_f1"] for item in report["baselines"])
    gate_checks = {
        "cross_validation_beats_baselines": selected["cv"]["mean"]["macro_f1"] >= best_baseline_cv + 0.01,
        "holdout_beats_baselines": selected["holdout"]["macro_f1"] >= best_baseline_test + 0.01,
        "holdout_recall_at_least_half": selected["holdout"]["recall"] >= 0.5,
        "at_least_ten_positive_holdout_examples": report["split"]["holdout_positive_examples"] >= 10,
        "at_least_ten_positive_holdout_patients": report["split"]["holdout_positive_patients"] >= 10,
    }
    ready = all(gate_checks.values())
    report.update({
        "status": "completed", "selection": {
            "model_id": selected["id"], "model_name": selected["name"],
            "criterion": "Mean patient-group cross-validation macro F1, then positive-class recall.",
            "prediction_enabled": ready, "gate_checks": gate_checks,
            "message": "Demonstration checks passed; predictions remain unvalidated synthetic research." if ready else "Not reliable enough for predictions; the comparison remains available for learning.",
            "gate_policy": "Fixed before evaluation: beat both baselines by 0.01 macro F1 in development and holdout, recall >= 0.50 and at least 10 independent patients with positive holdout outcomes. A gate is not clinical validation.",
        },
        "feature_importance": _importance(pipelines[selected["id"]], x[holdout], y[holdout], groups[holdout], seed),
        "feature_importance_method": "Five held-out permutation repeats after model selection. Importance is the change in patient-weighted macro F1 when a feature is shuffled; zero or negative changes show no demonstrated contribution. Correlated features share signal. This is not a medical cause or probability.",
    })
    directory.mkdir(parents=True, exist_ok=True)
    public = _public_report(report)
    joblib.dump({"version": VERSION, "selected": selected["id"], "pipelines": pipelines, "report": public}, directory / "model_bundle.joblib")
    _write_report(directory, public)
    return public


def predict_summary(rows, artifact_dir):
    """Aggregate latest in-window observations. Load only server-owned joblib files."""
    bundle = joblib.load(Path(artifact_dir) / "model_bundle.joblib")
    if bundle.get("version") != VERSION:
        raise ValueError("The saved model version is unsupported; retrain it.")
    report = bundle["report"]
    snapshots, excluded = _snapshots(list(rows), historical=False)
    latest = [visits[-1] for visits in snapshots.values() if visits]
    base = {
        "eligible_patients": _safe_count(len(latest)), "excluded_rows": _safe_counts(excluded),
        "prediction_enabled": report["selection"]["prediction_enabled"],
        "as_of": max(item[0] for item in latest).isoformat() if latest else None,
        "training_through": report["training_dates"]["through"],
        "interpretation": "Retrospective synthetic cohort estimates using each patient's latest selected observation; not live clinical forecasts.",
        "disclaimer": TARGET["disclaimer"], "counts": None,
    }
    if not base["prediction_enabled"]:
        return {**base, "reason": report["selection"]["message"]}
    if len(latest) < DISPLAY_MINIMUM:
        return {**base, "eligible_patients": None, "reason": "At least five patients are required for an aggregate result."}
    x = np.asarray([item[1] for item in latest], dtype=object)
    with threadpool_limits(limits=1):
        predicted = bundle["pipelines"][bundle["selected"]].predict(x)
    count = int((predicted == 1).sum())
    small = 0 < count < DISPLAY_MINIMUM or 0 < len(latest) - count < DISPLAY_MINIMUM
    return {**base, "counts": {"elevated": None if small else count, "below_threshold": None if small else len(latest) - count},
            "suppressed": small, "reason": "Small result groups are hidden." if small else None}


def cluster_patient_groups(rows, *, n_groups=3, seed=DEFAULT_SEED):
    """Describe similar latest readings; output centroids, never patient points."""
    snapshots, excluded = _snapshots(list(rows), historical=False)
    latest = [visits[-1] for visits in snapshots.values() if visits]
    base = {"algorithm": "K-Means", "status": "insufficient_data", "groups": [],
            "eligible_patients": _safe_count(len(latest)), "excluded_rows": _safe_counts(excluded),
            "features": [{"key": key, "label": LABELS[key]} for key in NUMERIC_FEATURES],
            "disclaimer": "Similar measurements do not imply the same diagnosis, severity or treatment."}
    if not isinstance(n_groups, int) or isinstance(n_groups, bool) or not 2 <= n_groups <= 6:
        raise ValueError("Choose two to six groups.")
    if len(latest) < max(30, n_groups * DISPLAY_MINIMUM):
        return {**base, "reason": "At least 30 patients with usable BP observations are required."}
    raw = np.asarray([item[1][:len(NUMERIC_FEATURES)] for item in latest], dtype=float)
    transform = Pipeline([("missing", SimpleImputer(strategy="median", keep_empty_features=True)), ("scale", StandardScaler())])
    with threadpool_limits(limits=1):
        values = transform.fit_transform(raw)
        distinct = len(np.unique(values, axis=0))
        if distinct < n_groups:
            return {**base, "reason": "The readings do not contain enough distinct profiles for the selected groups."}
        model = KMeans(n_clusters=n_groups, n_init=10, random_state=seed)
        labels = model.fit_predict(values)
        pca = PCA(n_components=2, random_state=seed).fit(values)
        centers = pca.transform(model.cluster_centers_)
        try:
            separation = silhouette_score(values, labels, sample_size=min(len(values), 1000), random_state=seed)
        except ValueError:
            separation = None
    groups = []
    for label in range(n_groups):
        chosen = labels == label
        size = int(chosen.sum())
        profile = {}
        for position, key in enumerate(NUMERIC_FEATURES):
            observed = raw[chosen, position]
            observed = observed[~np.isnan(observed)]
            profile[key] = {"mean": round(float(observed.mean()), 2) if len(observed) >= DISPLAY_MINIMUM else None,
                            "observations": int(len(observed)) if len(observed) >= DISPLAY_MINIMUM else None}
        disease_counts = Counter()
        for position in np.flatnonzero(chosen):
            codes = latest[int(position)][2].get("disease_codes") or []
            if isinstance(codes, list):
                disease_counts.update(set(str(code) for code in codes))
        groups.append({"group": label + 1, "label": f"Similar readings {label + 1}",
                       "patient_count": size if size >= DISPLAY_MINIMUM else None, "suppressed": size < DISPLAY_MINIMUM,
                       "profile": profile if size >= DISPLAY_MINIMUM else {},
                       "position": {"x": round(float(centers[label, 0]), 4), "y": round(float(centers[label, 1]), 4)} if size >= DISPLAY_MINIMUM else None,
                       "conditions": [{"code": code, "patient_count": count if count >= DISPLAY_MINIMUM else None} for code, count in sorted(disease_counts.items())] if size >= DISPLAY_MINIMUM else [],
                       "explanation": "Patients in this group have similar standardized measurements. Missing values were filled with cohort medians for grouping only."})
    return {**base, "status": "completed", "eligible_patients": None if any(row["suppressed"] for row in groups) else len(latest),
            "groups": groups, "silhouette": None if separation is None or any(row["suppressed"] for row in groups) else round(float(separation), 6),
            "pca": {"explained_variance": [round(float(v), 6) for v in pca.explained_variance_ratio_], "meaning": "Two-dimensional view of aggregate group centres; axes summarize several measurements, not health scores."},
            "missing_feature_counts": {key: _safe_count(int(np.isnan(raw[:, i]).sum())) for i, key in enumerate(NUMERIC_FEATURES)}}
