"""Extend only the dedicated synthetic database with seeded patient histories."""

from django.core.management.base import BaseCommand

from analytics.synthetic_generation import append_synthetic_patients


class Command(BaseCommand):
    help = "Append synthetic Mumbai patients; repeat seed/count adds nothing. Requires config.synthetic_settings."
    requires_system_checks = ()
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=3000, help="Total generated patients for this seed, not an incremental amount.")
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        result = append_synthetic_patients(count=options["count"], seed=options["seed"])
        self.stdout.write(self.style.SUCCESS(
            f"Created {result['created_patients']} synthetic patients, "
            f"{result['created_visits']} visits and {result['created_labs']} lab results; "
            f"{result['existing_patients']} already present for seed {result['seed']}. "
            "Existing patients and the original import manifest were preserved."
        ))
