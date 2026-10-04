from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("analytics", "0003_project_branding")]

    operations: ClassVar[list] = [
        migrations.AddField(model_name="mlrun", name="task", field=models.CharField(choices=[("blood_pressure", "Next-visit blood pressure"), ("disease", "Primary disease")], default="blood_pressure", max_length=24)),
        migrations.RemoveConstraint(model_name="mlrun", name="analytics_ml_single_flight"),
        migrations.RemoveConstraint(model_name="mlrun", name="analytics_ml_one_active_model"),
        migrations.AddConstraint(model_name="mlrun", constraint=models.UniqueConstraint(fields=("batch", "task"), condition=models.Q(status__in=["queued", "running"]), name="analytics_ml_single_flight")),
        migrations.AddConstraint(model_name="mlrun", constraint=models.UniqueConstraint(fields=("batch", "task"), condition=models.Q(is_active_model=True), name="analytics_ml_one_active_model")),
        migrations.AddConstraint(model_name="mlrun", constraint=models.CheckConstraint(condition=models.Q(task__in=["blood_pressure", "disease"]), name="analytics_ml_valid_task")),
    ]
