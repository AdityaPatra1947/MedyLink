"""Aggregate measurement grouping, isolated from Django and clinical permissions.

Only server-validated synthetic snapshots may be supplied here. Patient keys are
used to select one latest observation and never enter feature matrices or public
results. Blood pressure remains a measurement input to K-Means/PCA grouping;
this module does not train a classifier or predict future blood pressure.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

DEFAULT_SEED = 20261003
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


def _snapshots(rows):
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
        features = _features(row)
        if not _valid_bp(features):
            excluded["missing_or_invalid_bp"] += 1
            continue
        patients[str(row["patient_key"])].append((observed, features, row))
    result = {}
    for key, visits in patients.items():
        visits.sort(key=lambda value: value[0])
        # Simultaneous ambiguous observations cannot be chosen as group inputs.
        dates = Counter(value[0] for value in visits)
        result[key] = []
        for visit in visits:
            if dates[visit[0]] == 1:
                result[key].append(visit)
        excluded["ambiguous_simultaneous_rows"] += sum(count for count in dates.values() if count > 1)
    return result, dict(excluded)


def _safe_count(value):
    return None if 0 < value < DISPLAY_MINIMUM else int(value)


def _safe_counts(values):
    return {key: _safe_count(value) for key, value in values.items()}


def cluster_patient_groups(rows, *, n_groups=3, seed=DEFAULT_SEED):
    """Describe similar latest readings; output centroids, never patient points."""
    snapshots, excluded = _snapshots(list(rows))
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
                            "observations": len(observed) if len(observed) >= DISPLAY_MINIMUM else None}
        disease_counts = Counter()
        for position in np.flatnonzero(chosen):
            codes = latest[int(position)][2].get("disease_codes") or []
            if isinstance(codes, list):
                disease_counts.update({str(code) for code in codes})
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
