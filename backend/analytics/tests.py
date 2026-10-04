"""Synthetic-only analytics tests; config.test_settings uses an isolated database."""

import copy
import hashlib
import json
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import numpy as np
from accounts.models import SecurityEvent, User
from clinic.models import ClinicalEntry, Patient
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from .models import (
    AnalyticsRun,
    DatasetBatch,
    DiseaseCode,
    DiseaseObservation,
    EvaluationTruth,
    PatientAreaObservation,
    StationArea,
)

PREFIX = "/api/v1/admin/analytics/"
PASSWORD = "Analytics-isolated-test-passphrase!947"
FILTERS = {
    "dataset_id": "analytics_test",
    "disease_code": "DENGUE",
    "line": "",
    "station_id": "",
    "date_from": "2026-09-01",
    "date_to": "2026-09-29",
}


class AnalyticsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.batch = DatasetBatch.objects.create(
            key="analytics_test",
            synthetic=True,
            generator_version="test-1",
            seed=731,
            as_of=date(2026, 9, 29),
            observation_start=date(2025, 9, 30),
            manifest_hash="a" * 64,
            dataset_hash="b" * 64,
            patient_count=0,
            observation_count=0,
        )
        self.station = StationArea.objects.create(
            batch=self.batch,
            key="KURLA",
            name="Kurla",
            lines=["Central", "Harbour"],
            latitude=19.065,
            longitude=72.88,
        )
        self.western_station = StationArea.objects.create(
            batch=self.batch,
            key="BORIVALI",
            name="Borivali",
            lines=["Western"],
            latitude=19.23,
            longitude=72.857,
        )
        self.disease = DiseaseCode.objects.create(code="DENGUE", label="Dengue")
        self.other_disease = DiseaseCode.objects.create(code="ASTHMA", label="Asthma")
        self.admin = self.user("admin")
        self.client = self.browser(self.admin)
        self.sequence = 0

    def user(self, role, suffix="", verified=True):
        return User.objects.create_user(
            email=f"{role}{suffix}@analytics-test.test",
            password=PASSWORD,
            name=f"Synthetic {role} {suffix}",
            role=role,
            email_verified_at=timezone.now() if verified else None,
        )

    def browser(self, user=None):
        client = APIClient(enforce_csrf_checks=True)
        response = client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        client.credentials(HTTP_X_CSRFTOKEN=response.data["csrfToken"])
        if user is not None:
            response = client.post(
                "/api/v1/auth/login/",
                {"email": user.email, "password": PASSWORD},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)
        return client

    def patient(
        self,
        latitude=19.065,
        longitude=72.88,
        station=None,
        disease=None,
        when="2026-09-15T12:00:00+00:00",
        age_band="30s",
        group=None,
    ):
        self.sequence += 1
        user = self.user("patient", str(self.sequence))
        patient = Patient.objects.create(user=user, date_of_birth=date(1990, 1, 1))
        area = PatientAreaObservation.objects.create(
            batch=self.batch,
            patient=patient,
            source_key=f"PRIVATE-PAT-{self.sequence}",
            station=station or self.station,
            latitude=latitude,
            longitude=longitude,
            coordinate_source="synthetic_jitter",
            valid_at=self.batch.as_of,
        )
        self.observation(patient, area, disease=disease, when=when, age_band=age_band)
        if group is not None:
            EvaluationTruth.objects.create(
                batch=self.batch,
                patient=patient,
                primary_disease=disease or self.disease,
                planted_group=group,
            )
        self.batch.patient_count = self.sequence
        self.batch.observation_count = self.batch.observations.count()
        self.batch.save(update_fields=["patient_count", "observation_count"])
        return patient, area

    def observation(
        self,
        patient,
        area,
        disease=None,
        when="2026-09-15T12:00:00+00:00",
        age_band="30s",
        episode=None,
    ):
        disease = disease or self.disease
        entry = ClinicalEntry.objects.create(
            patient=patient,
            author=patient.user,
            kind="condition",
            name="Private fixture",
            notes="PRIVATE CLINICAL TEXT MUST NEVER LEAK",
            source="patient_reported",
        )
        return DiseaseObservation.objects.create(
            batch=self.batch,
            patient=patient,
            area=area,
            disease=disease,
            observed_at=datetime.fromisoformat(when),
            episode_key=episode or f"PRIVATE-EP-{patient.pk}-{disease.code}",
            import_key=f"PRIVATE-OBS-{entry.pk}",
            age_band=age_band,
            clinical_entry=entry,
        )

    def points(self, count=6, latitude=19.065, longitude=72.88, **kwargs):
        return [
            self.patient(latitude + i * 0.0001, longitude, **kwargs)
            for i in range(count)
        ]

    def summary(self, **filters):
        return self.client.get(PREFIX + "summary/", {**FILTERS, **filters})

    def api_run(self, kind="cluster", **values):
        return self.client.post(
            PREFIX + f"{kind}-runs/", {**FILTERS, **values}, format="json"
        )

    def assert_private_aggregate(self, payload):
        forbidden = {
            "patient_id",
            "patient_key",
            "source_key",
            "record_key",
            "episode_key",
            "import_key",
            "email",
            "phone",
            "address",
            "planted_group",
            "labels",
            "medical_record_id",
            "clinical_entry_id",
            "synthetic_latitude",
            "synthetic_longitude",
            "points",
            "patients",
        }

        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value), value)
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(payload)
        text = json.dumps(payload, default=str)
        self.assertNotIn("PRIVATE-", text)
        self.assertNotIn("PRIVATE CLINICAL", text)
        self.assertNotIn("@analytics-test.test", text)

    def test_cookie_authentication_and_admin_authorization_on_every_route(self):
        self.points()
        saved = self.api_run()
        self.assertEqual(saved.status_code, 201)
        paths = ["catalog/", "summary/", "cluster-runs/", "evaluation-runs/"]
        paths += [
            f"{kind}-runs/{saved.data['id']}/" for kind in ("cluster", "evaluation")
        ]
        for role in (None, "patient", "doctor", "pharmacist"):
            browser = self.browser(self.user(role) if role else None)
            for path in paths:
                with self.subTest(role=role, path=path):
                    response = (
                        browser.post(PREFIX + path, FILTERS, format="json")
                        if path.endswith("runs/")
                        else browser.get(PREFIX + path, FILTERS)
                    )
                    self.assertEqual(response.status_code, 401 if role is None else 403)
                    self.assertTrue(
                        {"code", "detail", "request_id"}.issubset(response.data)
                    )
        self.assertEqual(self.client.get(PREFIX + "catalog/").status_code, 200)

    def test_account_revocation_and_unverified_admin_block_existing_session(self):
        self.admin.email_verified_at = None
        self.admin.save(update_fields=["email_verified_at"])
        self.assertEqual(self.client.get(PREFIX + "catalog/").status_code, 401)
        self.admin.email_verified_at = timezone.now()
        self.admin.save(update_fields=["email_verified_at"])
        browser = self.browser(self.admin)
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])
        self.assertEqual(browser.get(PREFIX + "catalog/").status_code, 401)

    def test_cookie_mutations_require_csrf(self):
        browser = APIClient(enforce_csrf_checks=True)
        browser.cookies["access_token"] = self.client.cookies["access_token"].value
        for kind in ("cluster", "evaluation"):
            response = browser.post(PREFIX + f"{kind}-runs/", FILTERS, format="json")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "csrf_failed")
        self.assertEqual(AnalyticsRun.objects.count(), 0)

    def test_catalog_uses_reference_stations_and_synthetic_labels(self):
        self.points()
        response = self.client.get(PREFIX + "catalog/", {"dataset_id": self.batch.key})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["synthetic"])
        self.assertEqual(response.data["suppression_threshold"], 5)
        kurla = next(s for s in response.data["stations"] if s["station_id"] == "KURLA")
        self.assertEqual(set(kurla["lines"]), {"Central", "Harbour"})
        self.assertEqual(kurla["latitude"], self.station.latitude)
        self.assert_private_aggregate(response.data)
        self.assertIn("no-store", response["Cache-Control"])

    def test_empty_deployment_catalog_and_unknown_dataset(self):
        self.western_station.delete()
        self.station.delete()
        self.batch.delete()
        response = self.client.get(PREFIX + "catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["datasets"], [])
        self.assertEqual(response.data["stations"], [])
        self.assertEqual(self.summary().status_code, 404)

    def test_filters_reject_invalid_unknown_and_mismatched_values(self):
        invalid = [
            {"unexpected": "value"},
            {"date_from": "not-a-date"},
            {"date_from": "2026-09-30", "date_to": "2026-09-01"},
            {"date_from": "2020-01-01"},
            {"line": "Metro"},
            {"station_id": "NOT_A_STATION"},
            {"line": "Western", "station_id": "KURLA"},
            {"disease_code": "NOT_A_DISEASE"},
        ]
        for values in invalid:
            with self.subTest(values=values):
                response = self.summary(**values)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertTrue(
                    {"code", "detail", "request_id"}.issubset(response.data)
                )
        for values in [
            {"radius_km": 0.09},
            {"radius_km": 3.1},
            {"min_samples": 2},
            {"min_samples": 31},
            {"min_samples": 4.5},
            {"disease_code": ""},
            {"radius_km": "nan"},
            {"radius_km": "inf"},
        ]:
            with self.subTest(values=values):
                self.assertEqual(self.api_run(**values).status_code, 400)
        for values in [
            {"seed": -1},
            {"seed": 2147483648},
            {"stability_repeats": 2},
            {"stability_repeats": 9},
        ]:
            with self.subTest(values=values):
                self.assertEqual(
                    self.api_run(kind="evaluation", **values).status_code, 400
                )
        self.assertEqual(AnalyticsRun.objects.count(), 0)

    def test_latest_patient_disease_dedup_and_interchange_membership(self):
        for patient, area in self.points(
            6, when="2026-09-01T00:00:00+00:00", age_band="30s"
        ):
            self.observation(
                patient, area, when="2026-09-29T23:59:59+00:00", age_band="40s"
            )
            self.observation(
                patient, area, when="2026-08-01T10:00:00+00:00", age_band="30s"
            )
        response = self.summary()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["counts"]["distinct_patients"], 6)
        self.assertEqual(response.data["counts"]["patient_disease_pairs"], 6)
        self.assertEqual(response.data["counts"]["observations"], 12)
        self.assertEqual(
            response.data["counts"]["first_recorded_episodes_in_window"], 0
        )
        lines = {row["line"]: row["patient_count"] for row in response.data["lines"]}
        self.assertEqual(lines["Central"], 6)
        self.assertEqual(lines["Harbour"], 6)
        bands = {
            row["age_band"]: row["patient_count"] for row in response.data["age_bands"]
        }
        self.assertEqual(bands["40s"], 6)
        self.assertNotIn(bands.get("30s"), [6, 12])
        self.assertTrue(
            any("overlap" in note.lower() for note in response.data["notes"])
        )
        self.assert_private_aggregate(response.data)

    def test_all_disease_summary_counts_distinct_people_separately_from_pairs(self):
        for patient, area in self.points():
            self.observation(patient, area, disease=self.other_disease)
        response = self.summary(disease_code="")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["counts"]["distinct_patients"], 6)
        self.assertEqual(response.data["counts"]["patient_disease_pairs"], 12)
        self.assertEqual(response.data["counts"]["observations"], 12)
        self.assertEqual(
            {row["disease_code"] for row in response.data["diseases"]},
            {"DENGUE", "ASTHMA"},
        )

    def test_demographic_summary_uses_latest_observation_across_diseases(self):
        for patient, area in self.points(
            6,
            disease=self.other_disease,
            when="2026-09-01T12:00:00+00:00",
            age_band="30s",
        ):
            self.observation(
                patient,
                area,
                disease=self.disease,
                when="2026-09-15T12:00:00+00:00",
                age_band="30s",
            )
            self.observation(
                patient,
                area,
                disease=self.other_disease,
                when="2026-09-29T12:00:00+00:00",
                age_band="40s",
            )
        response = self.summary(disease_code="")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["counts"]["distinct_patients"], 6)
        self.assertEqual(response.data["counts"]["patient_disease_pairs"], 12)
        self.assertEqual(
            response.data["age_bands"],
            [
                {"age_band": "40s", "patient_count": 6, "suppressed": False},
            ],
        )

    def test_small_summary_cells_are_suppressed_and_zero_is_reported(self):
        self.points(4)
        response = self.summary()
        self.assertEqual(response.data["counts"]["distinct_patients"], None)
        self.assertEqual(response.data["counts"]["missing_coordinates"], 0)
        self.assertTrue(response.data["stations"][0]["suppressed"])
        self.assertIsNone(response.data["stations"][0]["patient_count"])
        empty = self.summary(date_from="2026-09-20")
        self.assertEqual(empty.data["counts"]["distinct_patients"], 0)

    def test_real_haversine_fit_uses_radians_and_kilometre_radius(self):
        from .services import fit_dbscan

        # Points ~111 metres apart fit a 500m radius. Treating degrees as radians
        # would put neighbours ~6km apart and turn every point into noise.
        points = np.array([[19.065 + i * 0.001, 72.88] for i in range(6)])
        labels = fit_dbscan(points, 0.5, 3)
        self.assertEqual(len(set(labels)), 1)
        self.assertNotEqual(labels[0], -1)
        distant = np.array([[18.0 + i * 0.2, 72.0] for i in range(6)])
        self.assertEqual(list(fit_dbscan(distant, 0.5, 3)), [-1] * 6)
        for invalid in (
            [[float("nan"), 72.0]],
            [[91.0, 72.0]],
            [[19.0, 181.0]],
            np.zeros((5001, 2)),
        ):
            with self.assertRaises(ValidationError):
                fit_dbscan(invalid, 0.5, 3)

    def test_cluster_empty_and_missing_coordinates_are_explicit(self):
        self.points(6, when="2026-08-15T12:00:00+00:00")
        empty = self.api_run()
        self.assertEqual(empty.status_code, 201, empty.data)
        self.assertEqual(empty.data["result"]["counts"]["eligible_patients"], 0)
        self.assertIsNone(empty.data["result"]["metrics"]["silhouette"]["value"])
        self.assertTrue(empty.data["result"]["metrics"]["silhouette"]["reason"])
        for _ in range(6):
            self.patient(latitude=None, longitude=None)
        # A changed input identity is deliberately a different cache version.
        self.batch.manifest_hash = "c" * 64
        self.batch.save(update_fields=["manifest_hash"])
        response = self.api_run()
        self.assertEqual(response.data["result"]["counts"]["missing_coordinates"], 6)
        self.assertEqual(response.data["result"]["counts"]["with_coordinates"], 0)

    def test_all_noise_and_one_cluster_have_undefined_silhouette(self):
        for index in range(6):
            self.patient(latitude=18.0 + index * 0.2, longitude=72.0)
        response = self.api_run()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["result"]["counts"]["cluster_count"], 0)
        self.assertEqual(response.data["result"]["counts"]["noise_patients"], 6)
        self.assertIsNone(response.data["result"]["metrics"]["silhouette"]["value"])
        self.assertTrue(response.data["result"]["metrics"]["silhouette"]["reason"])
        self.points(6)
        response = self.api_run(radius_km=0.6)
        self.assertEqual(response.data["result"]["counts"]["cluster_count"], 1)
        self.assertIsNone(response.data["result"]["metrics"]["silhouette"]["value"])
        self.assertTrue(response.data["result"]["metrics"]["silhouette"]["reason"])

    def test_suppressed_cluster_withholds_geometry_and_station_breakdown(self):
        self.points(4)
        response = self.api_run(min_samples=3)
        self.assertEqual(response.status_code, 201, response.data)
        cluster = response.data["result"]["clusters"][0]
        self.assertTrue(cluster["suppressed"])
        self.assertIsNone(cluster["patient_count"])
        self.assertIsNone(cluster["centroid"])
        self.assertIsNone(cluster["bounds"])
        self.assertEqual(cluster["stations"], [])
        self.assert_private_aggregate(response.data)

    def test_clusters_saved_reused_and_get_never_refits_or_reads_truth(self):
        self.points(6, group="PRIVATE-TRUTH-A")
        self.points(
            6,
            latitude=19.23,
            longitude=72.857,
            station=self.western_station,
            group="PRIVATE-TRUTH-B",
        )
        with patch.object(
            EvaluationTruth.objects,
            "filter",
            side_effect=AssertionError("ordinary fit read truth"),
        ):
            response = self.api_run()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["reused"])
        result = response.data["result"]
        self.assertEqual(result["counts"]["cluster_count"], 2)
        self.assertEqual(result["counts"]["clustered_patients"], 12)
        self.assertGreater(result["metrics"]["silhouette"]["value"], 0.9)
        for cluster in result["clusters"]:
            self.assertEqual(cluster["patient_count"], 6)
            self.assertFalse(cluster["suppressed"])
            for coordinate in cluster["centroid"].values():
                self.assertEqual(coordinate, round(coordinate, 3))
        with patch(
            "analytics.services.fit_dbscan",
            side_effect=AssertionError("saved run fitted again"),
        ):
            reused = self.api_run()
            fetched = self.client.get(PREFIX + f"cluster-runs/{response.data['id']}/")
        self.assertEqual(reused.status_code, 200)
        self.assertEqual(reused.data["id"], response.data["id"])
        self.assertTrue(reused.data["reused"])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.data["result"], result)
        self.assertEqual(AnalyticsRun.objects.count(), 1)
        self.assertEqual(
            self.client.get(
                PREFIX + f"evaluation-runs/{response.data['id']}/"
            ).status_code,
            404,
        )
        self.assert_private_aggregate(response.data)

    def test_evaluation_grid_reproducibility_and_truth_never_returned(self):
        self.points(8, group="PRIVATE-TRUTH-A")
        self.points(
            8,
            latitude=19.23,
            longitude=72.857,
            station=self.western_station,
            group="PRIVATE-TRUTH-B",
        )
        first = self.api_run(kind="evaluation", seed=19, stability_repeats=3)
        self.assertEqual(first.status_code, 201, first.data)
        result = first.data["result"]
        grid = result["grid"]
        self.assertEqual(len(grid), 16)
        self.assertEqual(
            {(row["radius_km"], row["min_samples"]) for row in grid},
            {
                (radius, minimum)
                for radius in (0.3, 0.5, 0.8, 1.2)
                for minimum in (4, 5, 8, 12)
            },
        )
        self.assertEqual(len(result["stability"]["repeats"]), 3)
        self.assertAlmostEqual(
            result["synthetic_pattern_recovery"]["adjusted_rand_index"]["value"], 1.0
        )
        again = self.api_run(kind="evaluation", seed=19, stability_repeats=3)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(first.data["id"], again.data["id"])
        self.assertEqual(result, again.data["result"])
        # A fresh computation with the same seed must reproduce the metrics too;
        # a cache hit alone would not exercise seeded subsets and perturbations.
        AnalyticsRun.objects.filter(pk=first.data["id"]).delete()
        recomputed = self.api_run(kind="evaluation", seed=19, stability_repeats=3)
        self.assertEqual(recomputed.status_code, 201)
        self.assertEqual(recomputed.data["result"], result)
        self.assert_private_aggregate(first.data)

    def test_evaluation_truth_coverage_excludes_other_primary_diseases(self):
        self.points(6, group="PRIVATE-DENGUE-TRUTH")
        for patient, area in self.points(
            6,
            latitude=19.23,
            longitude=72.857,
            disease=self.other_disease,
            group="PRIVATE-ASTHMA-TRUTH",
        ):
            self.observation(patient, area, disease=self.disease)
        response = self.api_run(kind="evaluation")
        self.assertEqual(response.status_code, 201, response.data)
        recovery = response.data["result"]["synthetic_pattern_recovery"]
        self.assertEqual(recovery["evaluated_patients"], 6)
        self.assertEqual(recovery["coverage"], 0.5)
        self.assert_private_aggregate(response.data)

    def test_evaluation_without_truth_explains_missing_recovery(self):
        self.points(6)
        response = self.api_run(kind="evaluation")
        self.assertEqual(response.status_code, 201, response.data)
        recovery = response.data["result"]["synthetic_pattern_recovery"]
        self.assertIsNone(recovery["adjusted_rand_index"]["value"])
        self.assertTrue(
            recovery.get("reason") or recovery["adjusted_rand_index"]["reason"]
        )


class AnalyticsImportTests(TestCase):
    """All ORM application tests run only on Django's temporary test database."""

    def setUp(self):
        local = settings.BASE_DIR.parent / ".local"
        local.mkdir(exist_ok=True)
        self.directory = TemporaryDirectory(prefix="analytics-import-test-", dir=local)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.mapping_path = self.root / "mapping.json"
        self.stamp = "2026-09-15T12:00:00+00:00"
        self.station = {
            "station_id": "KURLA",
            "station_name": "Kurla",
            "lines": ["Central", "Harbour"],
            "latitude": 19.065,
            "longitude": 72.88,
            "aliases": ["Kurla Junction"],
            "source_feature_ids": ["synthetic-station-reference"],
        }
        self.dataset = {
            "metadata": {"dataset_id": "analytics_import_test", "synthetic": True},
            "stations": [self.station],
            "patients": [],
        }
        self.mapping = {
            "dataset_id": "analytics_import_test",
            "synthetic": True,
            "entities": {"patients": {}, "entries": {}, "records": {}},
        }
        self.observations = []
        self.truth = {
            "dataset_id": "analytics_import_test",
            "evaluation_only": True,
            "labels": [],
        }
        self.patient_rows = []
        self.entry_rows = []
        for index in range(2):
            sid, eid = f"PAT{index}", f"PAT{index}-ENTRY1"
            user = User.objects.create_user(
                email=f"patient{index}@analytics-import.test",
                name="Synthetic fixture",
                role="patient",
            )
            patient = Patient.objects.create(user=user, date_of_birth=date(1990, 1, 1))
            entry = ClinicalEntry.objects.create(
                patient=patient,
                author=user,
                kind="condition",
                name="Synthetic Dengue",
                notes="Synthetic fixture only",
                source="patient_reported",
            )
            ClinicalEntry.objects.filter(pk=entry.pk).update(
                created_at=datetime.fromisoformat(self.stamp)
            )
            self.patient_rows.append(patient)
            self.entry_rows.append(entry)
            geography = {
                "station_id": "KURLA",
                "lines": ["Central", "Harbour"],
                "synthetic_latitude": 19.065 + index * 0.0001,
                "synthetic_longitude": 72.88,
                "coordinate_kind": "simulated_station_catchment_point",
            }
            self.dataset["patients"].append(
                {
                    "source_id": sid,
                    "profile": {"date_of_birth": "1990-01-01"},
                    "geography": geography,
                    "records": [],
                    "entries": [{"source_id": eid, "recorded_at": self.stamp}],
                }
            )
            self.mapping["entities"]["patients"][sid] = {"id": str(patient.pk)}
            self.mapping["entities"]["entries"][eid] = {"id": str(entry.pk)}
            self.observations.append(
                {
                    "dataset_id": "analytics_import_test",
                    "is_synthetic": True,
                    "patient_key": sid,
                    "record_key": eid,
                    "episode_key": f"{sid}-PRIMARY",
                    "disease_code": "DENGUE",
                    "observed_at": self.stamp,
                    "age_at_observation": 36,
                    "age_band": "30s",
                    "station_id": "KURLA",
                    "line_memberships": ["Central", "Harbour"],
                    "synthetic_latitude": geography["synthetic_latitude"],
                    "synthetic_longitude": geography["synthetic_longitude"],
                    "coordinate_kind": geography["coordinate_kind"],
                }
            )
            self.truth["labels"].append(
                {
                    "patient_key": sid,
                    "primary_disease_code": "DENGUE",
                    "planted_group": "SYNTHETIC_GROUP",
                    "evaluation_only": True,
                }
            )
        self.write_package()
        for index, patient in enumerate(self.patient_rows):
            SecurityEvent.objects.create(
                user=patient.user,
                event="synthetic_dataset_import",
                metadata={
                    "synthetic": True,
                    "dataset_id": "analytics_import_test",
                    "source_id": f"PAT{index}",
                    "dataset_sha256": self.mapping["dataset_sha256"],
                },
            )

    def write_package(self):
        payloads = {
            "dataset.json": json.dumps(self.dataset).encode(),
            "analytics_observations.jsonl": (
                "\n".join(json.dumps(row) for row in self.observations) + "\n"
            ).encode(),
            "evaluation_only_ground_truth.json": json.dumps(self.truth).encode(),
        }
        manifest = {
            "schema_version": 1,
            "generator_version": "fixture-1",
            "synthetic": True,
            "dataset_id": "analytics_import_test",
            "seed": 19,
            "as_of": "2026-09-29",
            "observation_start": "2025-09-30",
            "patient_count": 2,
            "files": {},
        }
        for filename, payload in payloads.items():
            (self.root / filename).write_bytes(payload)
            manifest["files"][filename] = {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        self.mapping["dataset_sha256"] = manifest["files"]["dataset.json"]["sha256"]
        self.mapping_path.write_text(json.dumps(self.mapping), encoding="utf-8")
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def load(self):
        from .importing import load_package

        return load_package(self.root, self.mapping_path)

    def test_package_validation_and_command_dry_run_make_no_database_queries(self):
        with self.assertNumQueries(0):
            package = self.load()
            output = StringIO()
            call_command(
                "import_synthetic_analytics",
                dataset_dir=str(self.root),
                mapping=str(self.mapping_path),
                stdout=output,
            )
        self.assertEqual(len(package["observations"]), 2)
        self.assertEqual(DatasetBatch.objects.count(), 0)
        self.assertIn("Dry run", output.getvalue())
        self.assertEqual(ClinicalEntry.objects.count(), 2)

    def test_apply_is_idempotent_and_preserves_clinical_records(self):
        from .importing import import_package

        package = self.load()
        original = list(ClinicalEntry.objects.order_by("pk").values())
        batch, created = import_package(package)
        self.assertTrue(created)
        same, created = import_package(package)
        self.assertFalse(created)
        self.assertEqual(batch.pk, same.pk)
        self.assertEqual(DatasetBatch.objects.count(), 1)
        self.assertEqual(StationArea.objects.count(), 1)
        self.assertEqual(PatientAreaObservation.objects.count(), 2)
        self.assertEqual(DiseaseObservation.objects.count(), 2)
        self.assertEqual(EvaluationTruth.objects.count(), 2)
        self.assertEqual(
            SecurityEvent.objects.filter(event="synthetic_analytics_import").count(), 1
        )
        self.assertEqual(list(ClinicalEntry.objects.order_by("pk").values()), original)
        self.assertEqual(User.objects.count(), 2)
        for observation in DiseaseObservation.objects.select_related(
            "clinical_entry", "area"
        ):
            self.assertEqual(
                observation.observed_at, observation.clinical_entry.created_at
            )
            self.assertEqual(
                observation.patient_id, observation.clinical_entry.patient_id
            )
            self.assertEqual(observation.patient_id, observation.area.patient_id)

    def test_manifest_hash_tampering_is_refused_offline(self):
        path = self.root / "analytics_observations.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        with (
            self.assertNumQueries(0),
            self.assertRaisesMessage(CommandError, "checksum"),
        ):
            self.load()
        self.assertEqual(DatasetBatch.objects.count(), 0)

    def test_wrong_clinical_mapping_hash_is_refused_offline(self):
        self.mapping["dataset_sha256"] = "0" * 64
        self.mapping_path.write_text(json.dumps(self.mapping), encoding="utf-8")
        with (
            self.assertNumQueries(0),
            self.assertRaisesMessage(CommandError, "exact dataset hash"),
        ):
            self.load()

    def test_existing_dataset_with_changed_inputs_is_never_overwritten(self):
        from .importing import import_package

        package = self.load()
        batch, _ = import_package(package)
        changed = copy.deepcopy(package)
        changed["manifest_hash"] = "c" * 64
        with self.assertRaisesMessage(CommandError, "different input hashes"):
            import_package(changed)
        batch.refresh_from_db()
        self.assertEqual(batch.manifest_hash, package["manifest_hash"])
        self.assertEqual(DiseaseObservation.objects.count(), 2)

    def test_missing_synthetic_lineage_is_refused_without_analytics_writes(self):
        from .importing import import_package

        SecurityEvent.objects.filter(user=self.patient_rows[0].user).delete()
        with self.assertRaisesMessage(CommandError, "lineage"):
            import_package(self.load())
        self.assertEqual(DatasetBatch.objects.count(), 0)
        self.assertEqual(ClinicalEntry.objects.count(), 2)

    def test_foreign_patient_clinical_source_is_refused(self):
        from .importing import import_package

        package = self.load()
        ClinicalEntry.objects.filter(pk=self.entry_rows[0].pk).update(
            patient=self.patient_rows[1]
        )
        with self.assertRaisesMessage(CommandError, "source relationship"):
            import_package(package)
        self.assertEqual(DatasetBatch.objects.count(), 0)

    def test_import_failure_rolls_back_all_sidecars_and_preserves_clinical_rows(self):
        from .importing import import_package

        with (
            patch.object(
                EvaluationTruth.objects,
                "bulk_create",
                side_effect=RuntimeError("fixture failure"),
            ),
            self.assertRaisesMessage(RuntimeError, "fixture failure"),
        ):
            import_package(self.load())
        self.assertEqual(DatasetBatch.objects.count(), 0)
        self.assertEqual(StationArea.objects.count(), 0)
        self.assertEqual(PatientAreaObservation.objects.count(), 0)
        self.assertEqual(DiseaseObservation.objects.count(), 0)
        self.assertEqual(DiseaseCode.objects.count(), 0)
        self.assertEqual(
            SecurityEvent.objects.filter(event="synthetic_analytics_import").count(), 0
        )
        self.assertEqual(Patient.objects.count(), 2)
        self.assertEqual(ClinicalEntry.objects.count(), 2)

    def test_unknown_fields_and_inconsistent_age_or_geography_are_rejected_offline(
        self,
    ):
        original = copy.deepcopy(self.observations)
        for change in (
            {"patient_name": "Should not be here"},
            {"age_band": "90s"},
            {"synthetic_latitude": 0.0},
            {"line_memberships": ["Western"]},
            {"record_key": "PAT1-ENTRY1"},
            {"observed_at": "2026-09-16T12:00:00+00:00"},
        ):
            with self.subTest(change=change):
                self.observations = copy.deepcopy(original)
                self.observations[0].update(change)
                self.write_package()
                with self.assertNumQueries(0), self.assertRaises(CommandError):
                    self.load()

    @override_settings(SYNTHETIC_IMPORT_ALLOWED=False)
    def test_command_apply_rejects_normal_settings_before_database_access(self):
        with (
            self.assertNumQueries(0),
            self.assertRaisesMessage(CommandError, "normal settings are refused"),
        ):
            call_command(
                "import_synthetic_analytics",
                dataset_dir=str(self.root),
                mapping=str(self.mapping_path),
                apply=True,
                stdout=StringIO(),
            )
        self.assertEqual(DatasetBatch.objects.count(), 0)

    def test_command_apply_and_repeat_use_identical_hashes(self):
        from .management.commands.import_synthetic_analytics import ClinicalImporter

        output = StringIO()
        # Only target selection is patched; all writes still go to the isolated
        # database installed by Django's test runner.
        with patch.object(ClinicalImporter, "require_target") as target_guard:
            for _ in range(2):
                call_command(
                    "import_synthetic_analytics",
                    dataset_dir=str(self.root),
                    mapping=str(self.mapping_path),
                    apply=True,
                    stdout=output,
                )
        self.assertEqual(target_guard.call_count, 2)
        self.assertIn("Already imported with identical hashes", output.getvalue())
        self.assertEqual(DatasetBatch.objects.count(), 1)
        self.assertEqual(DiseaseObservation.objects.count(), 2)

    def test_incomplete_coordinate_pair_is_rejected_offline(self):
        self.dataset["patients"][0]["geography"]["synthetic_latitude"] = None
        self.write_package()
        with (
            self.assertNumQueries(0),
            self.assertRaisesMessage(CommandError, "complete finite"),
        ):
            self.load()

    def test_entire_checked_in_dataset_validates_offline_without_clinical_database(
        self,
    ):
        from .importing import load_package

        dataset_dir = settings.BASE_DIR.parent / "data/synthetic/mumbai_stations_v1"
        data_bytes = (dataset_dir / "dataset.json").read_bytes()
        dataset = json.loads(data_bytes)
        mapping = {
            "dataset_id": dataset["metadata"]["dataset_id"],
            "synthetic": True,
            "dataset_sha256": hashlib.sha256(data_bytes).hexdigest(),
            "entities": {"patients": {}, "records": {}, "entries": {}},
        }
        for patient in dataset["patients"]:
            for category, sources in (
                ("patients", [patient]),
                ("records", patient.get("records", [])),
                ("entries", patient.get("entries", [])),
            ):
                for source in sources:
                    source_id = source["source_id"]
                    mapping["entities"][category][source_id] = {
                        "id": str(
                            uuid5(NAMESPACE_URL, f"offline-test/{category}/{source_id}")
                        ),
                    }
        mapping_path = self.root / "full-offline-mapping.json"
        mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
        with self.assertNumQueries(0):
            package = load_package(dataset_dir, mapping_path)
        self.assertEqual(len(package["patients"]), 1000)
        self.assertEqual(len(package["observations"]), 2394)
        self.assertEqual(len(package["truth"]), 1000)
        self.assertEqual(DatasetBatch.objects.count(), 0)
