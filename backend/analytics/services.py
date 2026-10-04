"""Bounded descriptive clustering; labels and person-level rows never leave here."""

import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np
import sklearn
from accounts.models import SecurityEvent
from django.db import transaction
from django.db.models import Count, Max, Min
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from sklearn.cluster import DBSCAN
from sklearn.metrics import adjusted_rand_score, silhouette_score

from .models import AnalyticsRun, DatasetBatch, DiseaseObservation, EvaluationTruth

EARTH_RADIUS_KM = 6371.0088
THRESHOLD = 5
MAX_POINTS = 5000
MAX_OBSERVATIONS = 50000
SERVICE_VERSION = "1.0.0"
LINES = ["Central", "Western", "Harbour"]
NOTES = [
    "Synthetic station-area distribution; not observed disease incidence, an outbreak or transmission evidence.",
    "Line memberships overlap; do not add line totals.",
    "Small-cell suppression is a display safeguard, not a guarantee against inference across overlapping filters.",
]


def safe_count(value):
    return None if 0 < value < THRESHOLD else int(value)


def safe_ratio(numerator, denominator):
    if (
        denominator < THRESHOLD
        or 0 < numerator < THRESHOLD
        or 0 < denominator - numerator < THRESHOLD
    ):
        return None
    return round(numerator / denominator, 6) if denominator else None


def metric(value=None, reason=None):
    return {
        "value": None if value is None else round(float(value), 6),
        "reason": reason,
    }


def versions():
    return {
        "service": SERVICE_VERSION,
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
    }


def live_dataset_metadata(batch):
    """Read append-aware coverage without rewriting the original import manifest."""
    observations = batch.observations.aggregate(
        count=Count("id"), last_id=Max("id"), first=Min("observed_at"), last=Max("observed_at"),
    )
    first = observations["first"].date() if observations["first"] else batch.observation_start
    last = observations["last"].date() if observations["last"] else batch.as_of
    return {
        "patient_count": batch.areas.count(),
        # Keep empty selections within the original published window valid.
        "observation_start": min(batch.observation_start, first),
        "as_of": max(batch.as_of, last),
        "observation_count": observations["count"],
        "last_observation_id": observations["last_id"],
    }


def resolve_filters(data):
    batch = get_object_or_404(DatasetBatch, key=data["dataset_id"], synthetic=True)
    metadata = live_dataset_metadata(batch)
    if data["date_to"] > metadata["as_of"] or data["date_from"] < metadata["observation_start"]:
        raise ValidationError(
            {"date_from": "Choose dates within this dataset's observation period."}
        )
    code = data.get("disease_code", "")
    if code and not batch.observations.filter(disease_id=code).exists():
        raise ValidationError(
            {"disease_code": "Choose a disease present in this dataset."}
        )
    station = data.get("station_id", "")
    if station:
        area = batch.stations.filter(key=station).first()
        if not area or (data.get("line") and data["line"] not in area.lines):
            raise ValidationError(
                {"station_id": "Choose a station in this dataset and selected line."}
            )
    filters = {
        key: value.isoformat() if isinstance(value, date) else value
        for key, value in data.items()
        if key
        in {"dataset_id", "disease_code", "line", "station_id", "date_from", "date_to"}
    }
    return batch, filters


def dataset_rows(batch):
    query = (
        DiseaseObservation.objects.filter(batch=batch)
        .select_related("area__station", "disease")
        .order_by("observed_at", "import_key")
    )
    if batch.observation_count > MAX_OBSERVATIONS:
        raise ValidationError(
            "This dataset exceeds the bounded demonstration observation limit."
        )
    rows = []
    for item in query[: MAX_OBSERVATIONS + 1]:
        rows.append(
            {
                "patient_id": item.patient_id,
                "disease_code": item.disease_id,
                "disease_label": item.disease.label,
                "observed_at": item.observed_at,
                "episode_key": item.episode_key,
                "import_key": item.import_key,
                "latitude": item.area.latitude,
                "longitude": item.area.longitude,
                "station_id": item.area.station.key,
                "station_name": item.area.station.name,
                "lines": item.area.station.lines,
                "age_band": item.age_band,
            }
        )
    if len(rows) > MAX_OBSERVATIONS:
        raise ValidationError(
            "This dataset exceeds the bounded demonstration observation limit."
        )
    return rows


def geography_matches(row, filters):
    return (
        (
            not filters.get("disease_code")
            or row["disease_code"] == filters["disease_code"]
        )
        and (not filters.get("line") or filters["line"] in row["lines"])
        and (
            not filters.get("station_id") or row["station_id"] == filters["station_id"]
        )
    )


def select_rows(all_rows, filters):
    start, end = (
        date.fromisoformat(filters["date_from"]),
        date.fromisoformat(filters["date_to"]),
    )
    selected, latest, first = [], {}, {}
    for row in all_rows:
        episode = (row["patient_id"], row["disease_code"], row["episode_key"])
        first.setdefault(episode, row)
        if (
            geography_matches(row, filters)
            and start <= row["observed_at"].date() <= end
        ):
            selected.append(row)
            latest[(row["patient_id"], row["disease_code"])] = row
    first_in_window = [
        row
        for row in first.values()
        if geography_matches(row, filters) and start <= row["observed_at"].date() <= end
    ]
    latest_rows = sorted(
        latest.values(), key=lambda row: (row["observed_at"], row["import_key"])
    )
    return latest_rows, selected, first_in_window


def cohort(batch, filters):
    rows, selected, first = select_rows(dataset_rows(batch), filters)
    return rows, len(selected), len(first)


def cells(groups, descriptor):
    result = []
    for key in sorted(groups):
        count = len(groups[key])
        result.append(
            {
                **descriptor(key),
                "patient_count": safe_count(count),
                "suppressed": 0 < count < THRESHOLD,
            }
        )
    return result


def summary(batch, filters):
    rows, selected, first = select_rows(dataset_rows(batch), filters)
    by_patient = {row["patient_id"]: row for row in rows}
    disease, station, line, age = (defaultdict(set) for _ in range(4))
    station_info, labels = {}, {}
    for row in rows:
        disease[row["disease_code"]].add(row["patient_id"])
        labels[row["disease_code"]] = row["disease_label"]
    for person, row in by_patient.items():
        station[row["station_id"]].add(person)
        station_info[row["station_id"]] = row
        for membership in set(row["lines"]):
            line[membership].add(person)
        age[row["age_band"]].add(person)
    weekly, first_weekly = defaultdict(set), defaultdict(set)
    for row in selected:
        day = row["observed_at"].date()
        weekly[day - timedelta(days=day.weekday())].add(row["patient_id"])
    for row in first:
        day = row["observed_at"].date()
        first_weekly[day - timedelta(days=day.weekday())].add(
            (row["patient_id"], row["disease_code"], row["episode_key"])
        )
    start, end = (
        date.fromisoformat(filters["date_from"]),
        date.fromisoformat(filters["date_to"]),
    )
    week = start - timedelta(days=start.weekday())
    weeks = []
    while week <= end:
        count = len(weekly[week])
        weeks.append(
            {
                "week_start": week.isoformat(),
                "patient_count": safe_count(count),
                "suppressed": 0 < count < THRESHOLD,
                "first_recorded_episode_count": safe_count(len(first_weekly[week])),
            }
        )
        week += timedelta(days=7)
    return {
        "synthetic": True,
        "dataset_id": batch.key,
        "filters": filters,
        "suppression_threshold": THRESHOLD,
        "counts": {
            "distinct_patients": safe_count(len(by_patient)),
            "observations": safe_count(len(selected)),
            "patient_disease_pairs": safe_count(len(rows)),
            "missing_coordinates": safe_count(
                sum(row["latitude"] is None for row in by_patient.values())
            ),
            "first_recorded_episodes_in_window": safe_count(len(first)),
        },
        "diseases": cells(
            disease, lambda key: {"disease_code": key, "label": labels[key]}
        ),
        "stations": cells(
            station,
            lambda key: {
                "station_id": key,
                "station_name": station_info[key]["station_name"],
                "lines": station_info[key]["lines"],
            },
        ),
        "lines": cells(line, lambda key: {"line": key}),
        "age_bands": cells(age, lambda key: {"age_band": key}),
        "weekly": weeks,
        "notes": NOTES
        + [
            "Weekly patient counts are distinct within each week and must not be added."
        ],
    }


def fit_dbscan(points_degrees, radius_km=0.5, min_samples=5):
    """Input order is latitude, longitude in degrees; eps is converted from km."""
    points = np.asarray(points_degrees, dtype=float)
    if points.size == 0:
        return np.array([], dtype=int)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) > MAX_POINTS:
        raise ValidationError("Clustering requires at most 5,000 coordinate pairs.")
    if (
        not np.isfinite(points).all()
        or (np.abs(points[:, 0]) > 90).any()
        or (np.abs(points[:, 1]) > 180).any()
    ):
        raise ValidationError(
            "Coordinates must be finite latitude/longitude degrees in range."
        )
    if (
        not math.isfinite(radius_km)
        or not 0.1 <= radius_km <= 3
        or not 3 <= min_samples <= 30
    ):
        raise ValidationError("Invalid DBSCAN radius or minimum sample count.")
    return DBSCAN(
        eps=radius_km / EARTH_RADIUS_KM,
        min_samples=min_samples,
        metric="haversine",
        algorithm="ball_tree",
        n_jobs=1,
    ).fit_predict(np.radians(points))


def coordinate_rows(rows):
    usable = [
        row
        for row in rows
        if row["latitude"] is not None and row["longitude"] is not None
    ]
    if len(usable) > MAX_POINTS:
        raise ValidationError(
            "Limit the cohort to at most 5,000 eligible coordinate pairs."
        )
    return usable, np.asarray(
        [[row["latitude"], row["longitude"]] for row in usable], dtype=float
    ).reshape(-1, 2)


def silhouette(points, labels):
    retained = labels >= 0
    n = int(retained.sum())
    clusters = len(set(labels[retained]))
    base = {"sample_size": safe_count(n), "coverage": safe_ratio(n, len(labels))}
    if len(labels) < THRESHOLD:
        return {
            **metric(reason="Cohort is below the five-patient display threshold."),
            **base,
        }
    if n == 0:
        return {
            **metric(
                reason="All eligible points are noise, or no coordinates are available."
            ),
            **base,
        }
    if clusters < 2:
        return {
            **metric(reason="Silhouette needs at least two non-noise clusters."),
            **base,
        }
    counts = Counter(int(label) for label in labels[retained])
    if any(size < THRESHOLD for size in counts.values()):
        return {
            **metric(reason="A non-noise cluster is below the display threshold."),
            **base,
        }
    if n <= clusters:
        return {
            **metric(reason="Silhouette requires more samples than cluster labels."),
            **base,
        }
    try:
        sample_size = min(n, 750)
        value = silhouette_score(
            np.radians(points[retained]),
            labels[retained],
            metric="haversine",
            sample_size=sample_size,
            random_state=20260929,
        )
        return {
            **metric(value),
            **base,
            "sample_size": sample_size,
            "sampling": "Uniform seeded sample of at most 750 non-noise points.",
        }
    except ValueError:
        return {
            **metric(
                reason="The bounded silhouette sample has insufficient label coverage."
            ),
            **base,
        }


def cluster_counts(rows, labels):
    n, noise = len(labels), int((labels == -1).sum())
    missing, clustered = len(rows) - n, n - noise
    # Avoid reconstructing a directly suppressed noise/missing cell from this envelope.
    related_small = any(0 < value < THRESHOLD for value in (noise, missing, clustered))
    return {
        "eligible_patients": None if related_small else safe_count(len(rows)),
        "with_coordinates": None if related_small else safe_count(n),
        "missing_coordinates": safe_count(missing),
        "clustered_patients": safe_count(clustered),
        "noise_patients": safe_count(noise),
        "cluster_count": len(set(labels) - {-1}),
    }


def clustering(rows, parameters):
    usable, points = coordinate_rows(rows)
    labels = fit_dbscan(points, parameters["radius_km"], parameters["min_samples"])
    clusters = []
    for label in sorted(set(labels) - {-1}):
        indices = np.flatnonzero(labels == label)
        size = len(indices)
        group = {
            "cluster": int(label),
            "patient_count": safe_count(size),
            "suppressed": size < THRESHOLD,
            "centroid": None,
            "bounds": None,
            "stations": [],
        }
        if size >= THRESHOLD:
            group_points = points[indices]
            group["centroid"] = {
                "latitude": round(float(group_points[:, 0].mean()), 3),
                "longitude": round(float(group_points[:, 1].mean()), 3),
            }
            group["bounds"] = dict(
                zip(
                    ("south", "north", "west", "east"),
                    [
                        round(float(v), 3)
                        for v in (
                            group_points[:, 0].min(),
                            group_points[:, 0].max(),
                            group_points[:, 1].min(),
                            group_points[:, 1].max(),
                        )
                    ],
                )
            )
            members, names = defaultdict(set), {}
            for index in indices:
                row = usable[int(index)]
                members[row["station_id"]].add(row["patient_id"])
                names[row["station_id"]] = row["station_name"]
            group["stations"] = cells(
                members,
                lambda key, names=names: {
                    "station_id": key,
                    "station_name": names[key],
                },
            )
        clusters.append(group)
    noise_fraction = safe_ratio(int((labels == -1).sum()), len(labels))
    return {
        "counts": cluster_counts(rows, labels),
        "metrics": {
            "noise_fraction": noise_fraction,
            "noise_fraction_reason": "Small-cell suppression or no eligible points."
            if noise_fraction is None
            else None,
            "silhouette": silhouette(points, labels),
        },
        "clusters": clusters,
        "notes": NOTES
        + [
            "DBSCAN eps is neighborhood reach, not a maximum cluster radius; connected chains can merge groups."
        ],
    }


def ari(reference, predicted):
    if len(reference) < THRESHOLD:
        return metric(reason="Fewer than five shared/evaluable patients.")
    if len(set(reference)) < 2 or len(set(predicted)) < 2:
        return metric(
            reason="Both partitions need at least two groups for a useful recovery comparison."
        )
    return metric(adjusted_rand_score(reference, predicted))


def evaluation(batch, rows, parameters):
    usable, points = coordinate_rows(rows)
    baseline = fit_dbscan(points, parameters["radius_km"], parameters["min_samples"])
    grid = []
    for radius in (0.3, 0.5, 0.8, 1.2):
        for minimum in (4, 5, 8, 12):
            labels = fit_dbscan(points, radius, minimum)
            grid.append(
                {
                    "radius_km": radius,
                    "min_samples": minimum,
                    "cluster_count": len(set(labels) - {-1}),
                    "noise_fraction": safe_ratio(
                        int((labels == -1).sum()), len(labels)
                    ),
                    "silhouette": silhouette(points, labels),
                }
            )
    repeats = []
    rng = np.random.default_rng(parameters["seed"])
    for iteration in range(parameters["stability_repeats"]):
        count = max(1, int(len(points) * 0.8)) if len(points) else 0
        selected = np.sort(rng.choice(len(points), count, replace=False))
        perturbed = points[selected].copy()
        if count:
            jitter = rng.normal(0, 0.03, size=(count, 2))
            perturbed[:, 0] += np.degrees(jitter[:, 0] / EARTH_RADIUS_KM)
            cosines = np.maximum(np.cos(np.radians(points[selected, 0])), 0.01)
            perturbed[:, 1] += np.degrees(jitter[:, 1] / (EARTH_RADIUS_KM * cosines))
            perturbed[:, 0] = np.clip(perturbed[:, 0], -90, 90)
            perturbed[:, 1] = (perturbed[:, 1] + 180) % 360 - 180
        prediction = fit_dbscan(
            perturbed, parameters["radius_km"], parameters["min_samples"]
        )
        repeats.append(
            {
                "repeat": iteration + 1,
                "shared_patients": safe_count(count),
                "retained_fraction": safe_ratio(count, len(points)),
                "noise_fraction": safe_ratio(
                    int((prediction == -1).sum()), len(prediction)
                ),
                "adjusted_rand_index": ari(
                    baseline[selected].tolist(), prediction.tolist()
                ),
            }
        )
    values = [
        row["adjusted_rand_index"]["value"]
        for row in repeats
        if row["adjusted_rand_index"]["value"] is not None
    ]
    # This is the only service path that reads planted labels, after all fits above.
    truth = {
        item.patient_id: item
        for item in EvaluationTruth.objects.filter(
            batch=batch, primary_disease_id=rows[0]["disease_code"] if rows else ""
        )
    }
    indices = [i for i, row in enumerate(usable) if row["patient_id"] in truth]
    reference = [truth[usable[i]["patient_id"]].planted_group for i in indices]
    recovery = ari(reference, baseline[indices].tolist())
    return {
        "grid": grid,
        "selected": {key: parameters[key] for key in ("radius_km", "min_samples")},
        "stability": {
            "seed": parameters["seed"],
            "subsample_fraction": 0.8,
            "perturbation_km": 0.03,
            "repeats": repeats,
            "mean_adjusted_rand_index": metric(float(np.mean(values)))
            if values
            else metric(reason="No repeat had a meaningful ARI."),
        },
        "synthetic_pattern_recovery": {
            "adjusted_rand_index": recovery,
            "evaluated_patients": safe_count(len(indices)),
            "coverage": safe_ratio(len(indices), len(usable)),
            "background_convention": "BACKGROUND is one reference group; all DBSCAN noise is one predicted group.",
            "reason": recovery["reason"],
        },
        "counts": cluster_counts(rows, baseline),
        "notes": NOTES
        + [
            "Synthetic pattern recovery is not diagnostic accuracy or evidence of real-world validity.",
            "The default September scenario is deliberately easy; use independently seeded, harder background/overlap scenarios before any generalization claim.",
            "The parameter grid is descriptive; no best parameter is selected automatically.",
        ],
    }


def run_payload(run, reused=False):
    return {
        "id": str(run.id),
        "kind": run.kind,
        "status": run.status,
        "reused": reused,
        "created_at": run.created_at.isoformat(),
        "synthetic": True,
        "dataset_id": run.batch.key,
        "filters": run.filters,
        "parameters": run.parameters,
        "runtime_ms": run.runtime_ms,
        "versions": run.versions,
        "result": run.result,
    }


def execute_run(batch, actor, kind, filters, parameters, request_id=""):
    library_versions = versions()
    # Serialize fits per batch so simultaneous requests cannot fit the same run twice.
    with transaction.atomic():
        DatasetBatch.objects.select_for_update().get(pk=batch.pk)
        metadata = live_dataset_metadata(batch)
        canonical = {
            "manifest": batch.manifest_hash,
            "input_hashes": batch.input_hashes,
            "append_revision": [metadata["observation_count"], metadata["last_observation_id"]],
            "kind": kind,
            "filters": filters,
            "parameters": parameters,
            "versions": library_versions,
        }
        cache_key = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing = (
            AnalyticsRun.objects.filter(cache_key=cache_key)
            .select_related("batch")
            .first()
        )
        if existing:
            return existing, True
        started = time.perf_counter()
        rows, _, _ = cohort(batch, filters)
        result = (
            evaluation(batch, rows, parameters)
            if kind == "evaluation"
            else clustering(rows, parameters)
        )
        run = AnalyticsRun.objects.create(
            batch=batch,
            actor=actor,
            kind=kind,
            cache_key=cache_key,
            filters=filters,
            parameters=parameters,
            versions=library_versions,
            result=result,
            runtime_ms=round((time.perf_counter() - started) * 1000),
        )
        SecurityEvent.objects.create(
            user=actor,
            event="analytics." + kind,
            request_id=request_id[:64],
            metadata={
                "synthetic": True,
                "dataset_id": batch.key,
                "run_id": str(run.id),
            },
        )
        return run, False
