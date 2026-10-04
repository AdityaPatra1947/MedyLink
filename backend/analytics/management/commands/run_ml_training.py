import json

from accounts.models import User
from django.core.management.base import BaseCommand, CommandError

from analytics.ml_dataset import build_dataset, resolve_ml_filters
from analytics.ml_serializers import MLFilters
from analytics.ml_services import (
    disease_source,
    enqueue_training,
    execute_training,
    run_payload,
)


class Command(BaseCommand):
    help = "Train disease models with current mapped clinical data. --dry-run reads aggregate coverage only; --sync trains and records an MLRun."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-id", default="mumbai_stations_v1")
        parser.add_argument("--date-from")
        parser.add_argument("--date-to")
        parser.add_argument("--disease-code", default="")
        parser.add_argument("--disease-codes", default="", help="Comma-separated disease codes (OR selection).")
        parser.add_argument("--disease-search", default="", help="Partial disease name; narrows any chosen codes.")
        parser.add_argument("--task", choices=["disease"], default="disease")
        parser.add_argument("--line", default="")
        parser.add_argument("--station-id", default="")
        parser.add_argument("--admin-email")
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--sync", action="store_true")

    def handle(self, *args, **options):
        if options["task"] != "disease":
            raise CommandError("Only disease model training is available.")
        serializer = MLFilters(data={key: options[key] for key in ("dataset_id", "date_from", "date_to", "disease_code", "disease_codes", "disease_search", "line", "station_id")})
        if not serializer.is_valid():
            raise CommandError("Invalid training filters.")
        batch, filters = resolve_ml_filters(serializer.validated_data)
        if options["dry_run"]:
            data = build_dataset(batch, filters)
            self.stdout.write(json.dumps({"dry_run": True, "task": options["task"], "source": data["source"], "disease_source": disease_source(data)}, indent=2))
            return
        admins = User.objects.filter(role="admin", is_active=True, email_verified_at__isnull=False)
        if options.get("admin_email"):
            admins = admins.filter(email__iexact=options["admin_email"])
        actor = admins.order_by("created_at").first()
        if actor is None:
            raise CommandError("An active verified administrator is required to record training.")
        run, reused = enqueue_training(batch, actor, filters, asynchronous=False, task=options["task"])
        if reused:
            raise CommandError("A training run is already queued or running. Wait for it or retry after an interrupted run expires.")
        run = execute_training(run.id)
        self.stdout.write(json.dumps(run_payload(run), indent=2))
        if run.status == "failed":
            raise CommandError("Training failed; the previous model was preserved.")
