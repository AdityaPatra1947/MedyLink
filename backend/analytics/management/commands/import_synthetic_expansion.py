from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from analytics.synthetic_fixture import DEFAULT_DIRECTORY, FixtureError, apply_fixture, load_fixture


class Command(BaseCommand):
    help = "Validate the public expansion offline; --apply appends only to the matching dedicated synthetic database."
    requires_system_checks = ()
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DIRECTORY)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            package = load_fixture(options["dataset_dir"])
        except FixtureError as exc:
            raise CommandError(str(exc)) from None
        if not options["apply"]:
            counts = package["manifest"]["counts"]
            self.stdout.write(self.style.SUCCESS(
                f"Dry run passed: {counts['patients']} expansion patients, {counts['visits']} visits. "
                "Complete manifest and row validation; no database access or writes."
            ))
            return
        result = apply_fixture(package)
        self.stdout.write(self.style.SUCCESS(
            f"Created {result['created_patients']} synthetic patients, {result['created_visits']} visits "
            f"and {result['created_labs']} labs; {result['existing_patients']} already present. "
            "Expansion accounts remain inactive with unusable passwords. Base data was preserved."
        ))
