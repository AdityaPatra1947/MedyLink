from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("analytics", "0004_mlrun_task")]

    # Preserve historical task values and reports. API and worker guards prevent
    # retired runs from being exposed or executed; this changes new-run defaults.
    operations: ClassVar[list] = [
        migrations.AlterField(
            model_name="mlrun",
            name="task",
            field=models.CharField(
                choices=[("disease", "Primary disease")],
                default="disease",
                max_length=24,
            ),
        ),
    ]
