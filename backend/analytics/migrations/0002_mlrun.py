import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analytics", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="MLRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(default="queued", max_length=20)),
                ("filters", models.JSONField(default=dict)),
                ("source_summary", models.JSONField(default=dict)),
                ("report", models.JSONField(default=dict)),
                ("error", models.CharField(blank=True, max_length=500)),
                ("is_active_model", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("started_at", models.DateTimeField(null=True)),
                ("finished_at", models.DateTimeField(null=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ml_runs", to="analytics.datasetbatch")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(model_name="mlrun", constraint=models.CheckConstraint(condition=models.Q(status__in=["queued", "running", "completed", "failed", "insufficient_data"]), name="analytics_ml_valid_status")),
        migrations.AddConstraint(model_name="mlrun", constraint=models.UniqueConstraint(fields=("batch",), condition=models.Q(status__in=["queued", "running"]), name="analytics_ml_single_flight")),
        migrations.AddConstraint(model_name="mlrun", constraint=models.UniqueConstraint(fields=("batch",), condition=models.Q(is_active_model=True), name="analytics_ml_one_active_model")),
    ]
