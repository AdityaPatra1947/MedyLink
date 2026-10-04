import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class DatasetBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=80, unique=True)
    synthetic = models.BooleanField(default=True)
    generator_version = models.CharField(max_length=40)
    seed = models.BigIntegerField()
    as_of = models.DateField()
    observation_start = models.DateField()
    manifest_hash = models.CharField(max_length=64)
    dataset_hash = models.CharField(max_length=64)
    input_hashes = models.JSONField(default=dict)
    patient_count = models.PositiveIntegerField()
    observation_count = models.PositiveIntegerField()
    imported_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints: ClassVar[list] = [
            models.CheckConstraint(
                condition=Q(synthetic=True), name="analytics_synthetic_only"
            )
        ]


class StationArea(models.Model):
    batch = models.ForeignKey(
        DatasetBatch, on_delete=models.PROTECT, related_name="stations"
    )
    key = models.CharField(max_length=80)
    name = models.CharField(max_length=150)
    aliases = models.JSONField(default=list)
    lines = models.JSONField(default=list)
    latitude = models.FloatField()
    longitude = models.FloatField()
    source_feature_ids = models.JSONField(default=list)
    provenance = models.JSONField(default=dict)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(
                fields=["batch", "key"], name="analytics_station_batch_key"
            ),
            models.CheckConstraint(
                condition=Q(
                    latitude__gte=-90,
                    latitude__lte=90,
                    longitude__gte=-180,
                    longitude__lte=180,
                ),
                name="analytics_station_coordinate_range",
            ),
        ]


class PatientAreaObservation(models.Model):
    batch = models.ForeignKey(
        DatasetBatch, on_delete=models.PROTECT, related_name="areas"
    )
    patient = models.ForeignKey("clinic.Patient", on_delete=models.PROTECT)
    source_key = models.CharField(max_length=100)
    station = models.ForeignKey(StationArea, on_delete=models.PROTECT)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    coordinate_source = models.CharField(max_length=60)
    valid_at = models.DateField()

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(
                fields=["batch", "patient"], name="analytics_patient_batch_area"
            ),
            models.UniqueConstraint(
                fields=["batch", "source_key"], name="analytics_area_source_unique"
            ),
            models.CheckConstraint(
                condition=(
                    Q(latitude__isnull=True, longitude__isnull=True)
                    | Q(
                        latitude__isnull=False,
                        longitude__isnull=False,
                        latitude__gte=-90,
                        latitude__lte=90,
                        longitude__gte=-180,
                        longitude__lte=180,
                    )
                ),
                name="analytics_area_coordinate_pair",
            ),
        ]


class DiseaseCode(models.Model):
    code = models.CharField(max_length=50, primary_key=True)
    label = models.CharField(max_length=150)


class DiseaseObservation(models.Model):
    batch = models.ForeignKey(
        DatasetBatch, on_delete=models.PROTECT, related_name="observations"
    )
    patient = models.ForeignKey("clinic.Patient", on_delete=models.PROTECT)
    area = models.ForeignKey(PatientAreaObservation, on_delete=models.PROTECT)
    disease = models.ForeignKey(DiseaseCode, on_delete=models.PROTECT)
    observed_at = models.DateTimeField()
    episode_key = models.CharField(max_length=150)
    import_key = models.CharField(max_length=180)
    age_band = models.CharField(max_length=12)
    medical_record = models.ForeignKey(
        "clinic.MedicalRecord", null=True, on_delete=models.PROTECT
    )
    clinical_entry = models.ForeignKey(
        "clinic.ClinicalEntry", null=True, on_delete=models.PROTECT
    )

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(
                fields=["batch", "import_key"], name="analytics_observation_import_key"
            ),
            models.CheckConstraint(
                condition=(
                    Q(medical_record__isnull=False, clinical_entry__isnull=True)
                    | Q(medical_record__isnull=True, clinical_entry__isnull=False)
                ),
                name="analytics_exactly_one_clinical_source",
            ),
        ]
        indexes: ClassVar[list] = [
            models.Index(
                fields=["batch", "disease", "observed_at"],
                name="analytics_disease_window_idx",
            )
        ]


class EvaluationTruth(models.Model):
    """Synthetic labels are never read by summary or clustering services."""

    batch = models.ForeignKey(
        DatasetBatch, on_delete=models.PROTECT, related_name="evaluation_truth"
    )
    patient = models.ForeignKey("clinic.Patient", on_delete=models.PROTECT)
    primary_disease = models.ForeignKey(DiseaseCode, on_delete=models.PROTECT)
    planted_group = models.CharField(max_length=100)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(
                fields=["batch", "patient"], name="analytics_truth_patient_unique"
            )
        ]


class AnalyticsRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(DatasetBatch, on_delete=models.PROTECT)
    kind = models.CharField(
        max_length=12, choices=[("cluster", "Cluster"), ("evaluation", "Evaluation")]
    )
    cache_key = models.CharField(max_length=64, unique=True)
    algorithm = models.CharField(max_length=50, default="DBSCAN/haversine")
    filters = models.JSONField()
    parameters = models.JSONField()
    versions = models.JSONField()
    status = models.CharField(max_length=12, default="completed")
    result = models.JSONField()
    runtime_ms = models.PositiveIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)


class MLRun(models.Model):
    """A durable training job. Clinical rows and credentials never enter its result."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(DatasetBatch, on_delete=models.PROTECT, related_name="ml_runs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    task = models.CharField(max_length=24, default="blood_pressure", choices=[("blood_pressure", "Next-visit blood pressure"), ("disease", "Primary disease")])
    status = models.CharField(max_length=20, default="queued")
    filters = models.JSONField(default=dict)
    source_summary = models.JSONField(default=dict)
    report = models.JSONField(default=dict)
    error = models.CharField(max_length=500, blank=True)
    is_active_model = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints: ClassVar[list] = [
            models.CheckConstraint(
                condition=Q(status__in=["queued", "running", "completed", "failed", "insufficient_data"]),
                name="analytics_ml_valid_status",
            ),
            models.UniqueConstraint(
                fields=["batch", "task"], condition=Q(status__in=["queued", "running"]),
                name="analytics_ml_single_flight",
            ),
            models.UniqueConstraint(
                fields=["batch", "task"], condition=Q(is_active_model=True),
                name="analytics_ml_one_active_model",
            ),
            models.CheckConstraint(condition=Q(task__in=["blood_pressure", "disease"]), name="analytics_ml_valid_task"),
        ]
        ordering: ClassVar[list] = ["-created_at", "-id"]
