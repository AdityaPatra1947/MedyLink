from django.utils import timezone
from rest_framework import serializers


class MLFilters(serializers.Serializer):
    dataset_id = serializers.RegexField(r"\A[A-Za-z0-9_]{1,80}\Z", default="mumbai_stations_v1")
    disease_code = serializers.RegexField(r"\A[A-Z0-9_]{1,50}\Z", allow_blank=True, default="")
    disease_codes = serializers.RegexField(r"\A[A-Z0-9_]{1,50}(?:,[A-Z0-9_]{1,50})*\Z", allow_blank=True, default="", max_length=650)
    disease_search = serializers.CharField(allow_blank=True, default="", max_length=80)
    line = serializers.ChoiceField(choices=["", "Central", "Western", "Harbour"], default="")
    station_id = serializers.RegexField(r"\A[A-Z0-9_]{1,80}\Z", allow_blank=True, default="")
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Unknown field." for key in sorted(unknown)})
        start, end = attrs.get("date_from"), attrs.get("date_to")
        if start and end and start > end:
            raise serializers.ValidationError({"date_to": "Choose an end date on or after the start date."})
        if (start and start.year < 1900) or (end and end > timezone.localdate()):
            raise serializers.ValidationError("Choose dates from 1900 through today.")
        return {**attrs, "date_from": start, "date_to": end}


class MLTrainingFilters(MLFilters):
    task = serializers.ChoiceField(choices=["disease"], default="disease")
