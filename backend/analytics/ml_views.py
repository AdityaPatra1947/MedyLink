from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .ml_dataset import ML_DISEASE_LABELS, resolve_ml_filters
from .ml_serializers import MLFilters, MLTrainingFilters
from .ml_services import enqueue_training, insights, run_payload
from .models import DatasetBatch, MLRun
from .services import LINES, live_dataset_metadata, safe_count
from .views import AdminAnalyticsView


def filters_from(data):
    serializer = MLFilters(data=data)
    serializer.is_valid(raise_exception=True)
    return resolve_ml_filters(serializer.validated_data)


class MLCatalogView(AdminAnalyticsView):
    def get(self, request):
        if set(request.query_params) - {"dataset_id"}:
            raise ValidationError("Catalog only accepts dataset_id.")
        batches = list(DatasetBatch.objects.filter(synthetic=True).order_by("key"))
        requested = request.query_params.get("dataset_id")
        batch = get_object_or_404(DatasetBatch, key=requested, synthetic=True) if requested else next((row for row in batches if row.key == "mumbai_stations_v1"), batches[0] if batches else None)
        coverage = {row.key: live_dataset_metadata(row) for row in batches}
        return Response({
            "synthetic": True, "suppression_threshold": 5,
            "datasets": [{"dataset_id": row.key, "as_of": coverage[row.key]["as_of"].isoformat(), "observation_start": coverage[row.key]["observation_start"].isoformat(), "patient_count": safe_count(coverage[row.key]["patient_count"])} for row in batches],
            "diseases": [{"disease_code": code, "label": label} for code, label in ML_DISEASE_LABELS.items()],
            "stations": [{"station_id": row.key, "station_name": row.name, "lines": row.lines, "latitude": row.latitude, "longitude": row.longitude} for row in batch.stations.order_by("name")] if batch else [],
            "lines": LINES,
            "defaults": {"dataset_id": batch.key if batch else "mumbai_stations_v1", "disease_code": "", "line": "", "station_id": "", "date_from": None, "date_to": None},
        })


class MLInsightsView(AdminAnalyticsView):
    def get(self, request):
        batch, filters = filters_from(request.query_params)
        return Response(insights(batch, filters))


class MLRunsView(AdminAnalyticsView):
    def get(self, request):
        serializer = MLTrainingFilters(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        task = data.pop("task")
        batch, _ = resolve_ml_filters(data)
        rows = list(MLRun.objects.filter(batch=batch, task=task).select_related("batch")[:10])
        return Response({"latest": run_payload(rows[0]) if rows else None, "active": run_payload(MLRun.objects.filter(batch=batch, task=task, is_active_model=True).select_related("batch").first()), "runs": [run_payload(row) for row in rows]})

    def post(self, request):
        serializer = MLTrainingFilters(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        task = data.pop("task")
        batch, filters = resolve_ml_filters(data)
        run, reused = enqueue_training(batch, request.user, filters, task=task, request_id=str(getattr(request, "request_id", "")))
        return Response({**run_payload(run), "reused": reused}, status=200 if reused else 202)


class MLRunView(AdminAnalyticsView):
    def get(self, request, pk):
        if request.query_params:
            raise ValidationError("Run status does not accept filters.")
        run = get_object_or_404(MLRun.objects.select_related("batch"), pk=pk, batch__synthetic=True)
        return Response(run_payload(run))
