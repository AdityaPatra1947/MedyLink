from datetime import timedelta

from accounts.permissions import IsAdministrator
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AnalyticsRun, DatasetBatch, DiseaseCode
from .serializers import ClusterInput, EvaluationInput, Filters
from .services import (
    LINES,
    THRESHOLD,
    execute_run,
    live_dataset_metadata,
    resolve_filters,
    run_payload,
    safe_count,
    summary,
)


class AdminAnalyticsView(APIView):
    permission_classes = (IsAdministrator,)


class CatalogView(AdminAnalyticsView):
    def get(self, request):
        if set(request.query_params) - {"dataset_id"}:
            raise ValidationError("Catalog only accepts dataset_id.")
        batches = list(DatasetBatch.objects.filter(synthetic=True).order_by("key"))
        requested = request.query_params.get("dataset_id", "mumbai_stations_v1")
        batch = next((item for item in batches if item.key == requested), None)
        if request.query_params.get("dataset_id") and batch is None:
            batch = get_object_or_404(DatasetBatch, key=requested, synthetic=True)
        if batch is None and batches:
            batch = batches[0]
        metadata = {item.pk: live_dataset_metadata(item) for item in batches}
        current = metadata.get(batch.pk) if batch else None
        stations = (
            [
                {
                    "station_id": s.key,
                    "station_name": s.name,
                    "lines": s.lines,
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                }
                for s in batch.stations.order_by("name")
            ]
            if batch
            else []
        )
        codes = (
            DiseaseCode.objects.filter(diseaseobservation__batch=batch)
            .distinct()
            .order_by("label")
            if batch
            else []
        )
        return Response(
            {
                "synthetic": True,
                "suppression_threshold": THRESHOLD,
                "datasets": [
                    {
                        "dataset_id": item.key,
                        "as_of": metadata[item.pk]["as_of"].isoformat(),
                        "observation_start": metadata[item.pk]["observation_start"].isoformat(),
                        "generator_version": item.generator_version,
                        "patient_count": safe_count(metadata[item.pk]["patient_count"]),
                    }
                    for item in batches
                ],
                "diseases": [
                    {"disease_code": item.code, "label": item.label} for item in codes
                ],
                "stations": stations,
                "lines": LINES,
                "defaults": {
                    "dataset_id": batch.key if batch else "mumbai_stations_v1",
                    "disease_code": "DENGUE",
                    "line": "",
                    "station_id": "",
                    "date_from": max(current["observation_start"], current["as_of"] - timedelta(days=28)).isoformat() if current else "2026-09-01",
                    "date_to": current["as_of"].isoformat() if current else "2026-09-29",
                    "radius_km": 0.5,
                    "min_samples": 5,
                },
            }
        )


class SummaryView(AdminAnalyticsView):
    def get(self, request):
        serializer = Filters(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        batch, filters = resolve_filters(serializer.validated_data)
        return Response(summary(batch, filters))


class ClusterRunsView(AdminAnalyticsView):
    kind = "cluster"
    serializer_class = ClusterInput

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        batch, filters = resolve_filters(data)
        parameters = {
            key: data[key]
            for key in ("radius_km", "min_samples", "seed", "stability_repeats")
            if key in data
        }
        run, reused = execute_run(
            batch,
            request.user,
            self.kind,
            filters,
            parameters,
            str(getattr(request, "request_id", "")),
        )
        return Response(run_payload(run, reused), status=200 if reused else 201)


class EvaluationRunsView(ClusterRunsView):
    kind = "evaluation"
    serializer_class = EvaluationInput


class RunView(AdminAnalyticsView):
    kind = "cluster"

    def get(self, request, pk):
        run = get_object_or_404(
            AnalyticsRun.objects.select_related("batch"),
            pk=pk,
            kind=self.kind,
            batch__synthetic=True,
        )
        return Response(run_payload(run, True))


class EvaluationRunView(RunView):
    kind = "evaluation"
