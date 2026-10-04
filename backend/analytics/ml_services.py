"""Admin-only ML orchestration; the clinical application's access rules stay intact."""

import hashlib
import importlib
import logging
import math
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from accounts.models import SecurityEvent
from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .ml_dataset import build_dataset, summarize_cohort
from .models import DatasetBatch, MLRun
from .services import clustering

LOGGER = logging.getLogger(__name__)
DISCLAIMER = "These synthetic-data predictions support learning and decisions; they are not a diagnosis or a treatment recommendation."
_executor = None
_executor_lock = threading.Lock()


def pipeline():
    root = str(settings.BASE_DIR.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("ml.pipeline")


def artifact_dir(run):
    """DB-scoped paths prevent normal, synthetic and rehearsal model cross-use."""
    db = settings.DATABASES["default"]
    host = str(db.get("HOST", "")).lower()
    if host.endswith(".neon.tech"):
        first, separator, remaining = host.partition(".")
        host = first.removesuffix("-pooler") + separator + remaining
    identity = hashlib.sha256((host + ":" + str(db.get("PORT") or "5432") + "/" + str(db.get("NAME", ""))).encode()).hexdigest()[:20]
    root = Path(os.getenv("ML_ARTIFACT_ROOT") or getattr(settings, "ML_ARTIFACT_ROOT", "") or settings.BASE_DIR.parent / ".local" / "ml")
    return root / identity / str(run.id)


def public_json(value):
    """Reject identity-bearing payloads and replace non-finite numeric results."""
    forbidden = {"patient_id", "patient_key", "account_id", "health_id", "email", "phone", "address", "record_id", "source_key", "doctor_id", "planted_group"}
    if isinstance(value, dict):
        if forbidden.intersection(value):
            raise ValueError("Individual identities cannot be returned by ML insights.")
        return {str(key): public_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [public_json(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "item"):
        return public_json(value.item())
    raise ValueError("Unsupported ML result type.")


def run_payload(run):
    if run is None:
        return None
    messages = {
        "queued": "Waiting to train with the selected data.",
        "running": "Comparing four prediction methods on the same patient-separated data.",
        "completed": "Training finished. The selected model is available for these insights.",
        "failed": "Training did not finish. The previous successful model remains available.",
        "insufficient_data": "This selection does not have enough usable patient histories and outcomes to compare models reliably.",
    }
    if run.status == "completed" and run.report.get("selection", {}).get("prediction_enabled") is not True:
        messages["completed"] = "Model comparison finished, but the selected model did not pass the demonstration reliability checks. Predictions are unavailable."
    return public_json({
        "id": str(run.id), "status": run.status, "dataset_id": run.batch.key,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "filters": run.filters, "source": run.source_summary, "error": run.error or None,
        "message": messages[run.status], "report": run.report, "is_active_model": run.is_active_model,
    })


def enqueue_training(batch, actor, filters, *, asynchronous=True, request_id=""):
    with transaction.atomic():
        DatasetBatch.objects.select_for_update().get(pk=batch.pk)
        # An interrupted local process must not leave training blocked forever.
        cutoff = timezone.now() - timedelta(minutes=30)
        MLRun.objects.filter(batch=batch, status__in=["queued", "running"], created_at__lt=cutoff).update(status="failed", error="The previous training process was interrupted. Please retrain.", finished_at=timezone.now())
        pending = MLRun.objects.filter(batch=batch, status__in=["queued", "running"]).first()
        if pending:
            return pending, True
        if MLRun.objects.filter(status__in=["queued", "running"]).count() >= 2:
            raise ValidationError("The local training worker is busy. Wait for a current run to finish.")
        run = MLRun.objects.create(batch=batch, actor=actor, filters=filters)
        SecurityEvent.objects.create(user=actor, event="analytics.ml.queued", request_id=request_id[:64], metadata={"run_id": str(run.id), "synthetic": True})
        if asynchronous:
            transaction.on_commit(lambda: submit_training(run.id))
    return run, False


def submit_training(run_id):
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="medylink-ml")
        return _executor.submit(execute_training, run_id)


def execute_training(run_id):
    """Claim once, fit outside transactions, publish only a complete artifact."""
    close_old_connections()
    try:
        with transaction.atomic():
            run = MLRun.objects.select_for_update().select_related("batch").get(pk=run_id)
            if run.status != "queued":
                return run
            run.status, run.started_at = "running", timezone.now()
            run.save(update_fields=["status", "started_at"])
        data = build_dataset(run.batch, run.filters)
        report = public_json(pipeline().train_and_evaluate(data["history"], artifact_dir(run)))
        status = "completed" if report.get("status") == "completed" else "insufficient_data"
        if status == "completed" and not (artifact_dir(run) / "model_bundle.joblib").is_file():
            raise RuntimeError("Training did not produce a complete model artifact.")
        with transaction.atomic():
            DatasetBatch.objects.select_for_update().get(pk=run.batch_id)
            locked = MLRun.objects.select_for_update().get(pk=run_id)
            if locked.status != "running":
                return locked
            if status == "completed":
                MLRun.objects.filter(batch=run.batch, is_active_model=True).update(is_active_model=False)
                locked.is_active_model = True
            locked.status, locked.finished_at = status, timezone.now()
            locked.report, locked.source_summary = report, public_json(data["source"])
            locked.save(update_fields=["status", "finished_at", "report", "source_summary", "is_active_model"])
            SecurityEvent.objects.create(user_id=run.actor_id, event="analytics.ml." + status, metadata={"run_id": str(run.id), "synthetic": True})
        return locked
    except Exception:
        # Exceptions may contain file paths or source data. Keep diagnostics and
        # user messages generic; the stored public report is the review artifact.
        LOGGER.warning("A local ML training run failed; the previous model was preserved.")
        MLRun.objects.filter(pk=run_id, status__in=["queued", "running"]).update(status="failed", error="Training could not complete. Check the local worker and available training data, then retry.", finished_at=timezone.now())
        return MLRun.objects.select_related("batch").get(pk=run_id)
    finally:
        close_old_connections()


def current_hotspots(rows):
    # One private synthetic coordinate per patient. Only suppressed aggregates
    # leave clustering(); missing points remain missing rather than imputed.
    latest = {}
    for row in rows:
        if row["patient_key"] not in latest or row["observed_at"] > latest[row["patient_key"]]["observed_at"]:
            latest[row["patient_key"]] = row
    points = [{**row, "patient_id": row["patient_key"]} for row in latest.values()]
    result = clustering(points, {"radius_km": 0.5, "min_samples": 5})
    result["algorithm"] = "DBSCAN"
    result["explanation"] = "Groups nearby station areas with at least five selected patients. These synthetic case concentrations do not prove an outbreak."
    result["notes"] += ["This page uses current clinical observations and private simulated station-area points. Only rounded group locations are displayed; missing locations remain excluded."]
    return result


def insights(batch, filters):
    data = build_dataset(batch, filters)
    active = MLRun.objects.filter(batch=batch, is_active_model=True, status="completed").select_related("batch").first()
    training = MLRun.objects.filter(batch=batch, status__in=["queued", "running"]).select_related("batch").first()
    prediction = {"status": "unavailable", "reason": "Train the models to see an aggregate next-visit blood-pressure prediction."}
    if active:
        try:
            prediction = pipeline().predict_summary(data["cohort"], artifact_dir(active))
        except Exception:
            prediction = {"status": "unavailable", "reason": "The saved model is unavailable in this environment. Retrain to restore predictions."}
    groups = pipeline().cluster_patient_groups(data["cohort"])
    return public_json({
        "synthetic": True, "filters": filters, "source": data["source"], "summary": summarize_cohort(data["cohort"]),
        "prediction": prediction, "patient_groups": groups, "hotspots": current_hotspots(data["cohort"]),
        "model": run_payload(active), "training": run_payload(training),
        "suppression_threshold": 5,
        "notes": [DISCLAIMER, "All history is selected when dates are empty. Dates and other filters change the cohort; saved model comparison results retain their own training period.", "Counts below five are hidden. Overlapping filters still require careful interpretation.", "Disease labels are a limited mapping of recorded diagnoses and conditions, not predictions. Unknown text is not converted to a guessed disease."],
    })
