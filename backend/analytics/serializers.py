import math
from datetime import date

from rest_framework import serializers


class Filters(serializers.Serializer):
    dataset_id = serializers.RegexField(
        r"\A[A-Za-z0-9_]{1,80}\Z", default="mumbai_stations_v1"
    )
    disease_code = serializers.RegexField(
        r"\A[A-Z0-9_]{1,50}\Z", allow_blank=True, default=""
    )
    line = serializers.ChoiceField(
        choices=["", "Central", "Western", "Harbour"], default=""
    )
    station_id = serializers.RegexField(
        r"\A[A-Z0-9_]{1,80}\Z", allow_blank=True, default=""
    )
    date_from = serializers.DateField(default=date(2026, 9, 1))
    date_to = serializers.DateField(default=date(2026, 9, 29))

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "Unknown field." for key in sorted(unknown)}
            )
        if (
            attrs["date_from"] > attrs["date_to"]
            or (attrs["date_to"] - attrs["date_from"]).days > 365
        ):
            raise serializers.ValidationError(
                {"date_to": "Choose an ordered window of at most 366 days."}
            )
        return attrs


class ClusterInput(Filters):
    disease_code = serializers.RegexField(r"\A[A-Z0-9_]{1,50}\Z", default="DENGUE")
    radius_km = serializers.FloatField(default=0.5, min_value=0.1, max_value=3)
    min_samples = serializers.IntegerField(default=5, min_value=3, max_value=30)

    def validate_radius_km(self, value):
        if not math.isfinite(value):
            raise serializers.ValidationError("Enter a finite radius in kilometers.")
        return value


class EvaluationInput(ClusterInput):
    seed = serializers.IntegerField(default=20260929, min_value=0, max_value=2147483647)
    stability_repeats = serializers.IntegerField(default=3, min_value=3, max_value=8)
