from pathlib import Path

from clinic.management.commands.import_synthetic_dataset import (
    Command as ClinicalImporter,
)
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from analytics.importing import import_package, load_package


class Command(BaseCommand):
    help = "Validate synthetic analytics sidecars offline; --apply appends to the dedicated synthetic database."
    requires_system_checks = ()
    requires_migrations_checks = False

    def add_arguments(self, parser):
        root = settings.BASE_DIR.parent
        parser.add_argument(
            "--dataset-dir", default=str(root / "data/synthetic/mumbai_stations_v1")
        )
        parser.add_argument(
            "--mapping",
            default=str(root / ".local/synthetic/mumbai_stations_v1/import-map.json"),
        )
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        mapping = Path(options["mapping"]).expanduser().resolve()
        local = (settings.BASE_DIR.parent / ".local").resolve()
        if not mapping.is_relative_to(local) or mapping == local:
            raise CommandError(
                "Clinical mapping must be inside the ignored .local directory."
            )
        package = load_package(
            Path(options["dataset_dir"]).expanduser().resolve(), mapping
        )
        if not options["apply"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run passed: {len(package['patients'])} patients, {len(package['observations'])} structured observations. No database access or writes."
                )
            )
            return
        ClinicalImporter().require_target()
        batch, created = import_package(package)
        action = "Imported" if created else "Already imported with identical hashes"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {batch.key}; {batch.patient_count} patients, {batch.observation_count} observations."
            )
        )
