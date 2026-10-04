import uuid
from typing import ClassVar

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: ClassVar[list] = [
        ("clinic", "0005_patient_health_tracking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations: ClassVar[list] = [
        migrations.CreateModel(
            name="DiseaseCode",
            fields=[
                (
                    "code",
                    models.CharField(max_length=50, primary_key=True, serialize=False),
                ),
                ("label", models.CharField(max_length=150)),
            ],
        ),
        migrations.CreateModel(
            name="DatasetBatch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key", models.CharField(max_length=80, unique=True)),
                ("synthetic", models.BooleanField(default=True)),
                ("generator_version", models.CharField(max_length=40)),
                ("seed", models.BigIntegerField()),
                ("as_of", models.DateField()),
                ("observation_start", models.DateField()),
                ("manifest_hash", models.CharField(max_length=64)),
                ("dataset_hash", models.CharField(max_length=64)),
                ("input_hashes", models.JSONField(default=dict)),
                ("patient_count", models.PositiveIntegerField()),
                ("observation_count", models.PositiveIntegerField()),
                (
                    "imported_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("synthetic", True)),
                        name="analytics_synthetic_only",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="AnalyticsRun",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[("cluster", "Cluster"), ("evaluation", "Evaluation")],
                        max_length=12,
                    ),
                ),
                ("cache_key", models.CharField(max_length=64, unique=True)),
                (
                    "algorithm",
                    models.CharField(default="DBSCAN/haversine", max_length=50),
                ),
                ("filters", models.JSONField()),
                ("parameters", models.JSONField()),
                ("versions", models.JSONField()),
                ("status", models.CharField(default="completed", max_length=12)),
                ("result", models.JSONField()),
                ("runtime_ms", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="analytics.datasetbatch",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="StationArea",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(max_length=80)),
                ("name", models.CharField(max_length=150)),
                ("aliases", models.JSONField(default=list)),
                ("lines", models.JSONField(default=list)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("source_feature_ids", models.JSONField(default=list)),
                ("provenance", models.JSONField(default=dict)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stations",
                        to="analytics.datasetbatch",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PatientAreaObservation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("source_key", models.CharField(max_length=100)),
                ("latitude", models.FloatField(null=True)),
                ("longitude", models.FloatField(null=True)),
                ("coordinate_source", models.CharField(max_length=60)),
                ("valid_at", models.DateField()),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="areas",
                        to="analytics.datasetbatch",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="clinic.patient"
                    ),
                ),
                (
                    "station",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="analytics.stationarea",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="EvaluationTruth",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("planted_group", models.CharField(max_length=100)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="evaluation_truth",
                        to="analytics.datasetbatch",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="clinic.patient"
                    ),
                ),
                (
                    "primary_disease",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="analytics.diseasecode",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("batch", "patient"),
                        name="analytics_truth_patient_unique",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="DiseaseObservation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("observed_at", models.DateTimeField()),
                ("episode_key", models.CharField(max_length=150)),
                ("import_key", models.CharField(max_length=180)),
                ("age_band", models.CharField(max_length=12)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="observations",
                        to="analytics.datasetbatch",
                    ),
                ),
                (
                    "clinical_entry",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="clinic.clinicalentry",
                    ),
                ),
                (
                    "disease",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="analytics.diseasecode",
                    ),
                ),
                (
                    "medical_record",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="clinic.medicalrecord",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="clinic.patient"
                    ),
                ),
                (
                    "area",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="analytics.patientareaobservation",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["batch", "disease", "observed_at"],
                        name="analytics_disease_window_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("batch", "import_key"),
                        name="analytics_observation_import_key",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("clinical_entry__isnull", True),
                                ("medical_record__isnull", False),
                            ),
                            models.Q(
                                ("clinical_entry__isnull", False),
                                ("medical_record__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="analytics_exactly_one_clinical_source",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="stationarea",
            constraint=models.UniqueConstraint(
                fields=("batch", "key"), name="analytics_station_batch_key"
            ),
        ),
        migrations.AddConstraint(
            model_name="stationarea",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("latitude__gte", -90),
                    ("latitude__lte", 90),
                    ("longitude__gte", -180),
                    ("longitude__lte", 180),
                ),
                name="analytics_station_coordinate_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="patientareaobservation",
            constraint=models.UniqueConstraint(
                fields=("batch", "patient"), name="analytics_patient_batch_area"
            ),
        ),
        migrations.AddConstraint(
            model_name="patientareaobservation",
            constraint=models.UniqueConstraint(
                fields=("batch", "source_key"), name="analytics_area_source_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="patientareaobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("latitude__isnull", True), ("longitude__isnull", True)),
                    models.Q(
                        ("latitude__gte", -90),
                        ("latitude__isnull", False),
                        ("latitude__lte", 90),
                        ("longitude__gte", -180),
                        ("longitude__isnull", False),
                        ("longitude__lte", 180),
                    ),
                    _connector="OR",
                ),
                name="analytics_area_coordinate_pair",
            ),
        ),
    ]
