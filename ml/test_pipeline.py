"""No database or external services: aggregate measurement-grouping checks."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from ml.pipeline import FEATURES, cluster_patient_groups


def fixture(people=150):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = []
    for person in range(people):
        elevated = person % 2
        for visit in range(3):
            day = start + timedelta(days=visit * 30)
            result.append({
                "patient_key": f"PRIVATE-PATIENT-{person}",
                "observed_at": day.isoformat(), "available_at": day.isoformat(),
                "age": 25 + person % 50, "gender": "female" if person % 3 else "male",
                "systolic": 146 + person % 8 if elevated else 112 + person % 10,
                "diastolic": 92 if elevated else 74, "pulse": 70 + person % 20,
                "temperature": 36.5 + (person % 4) * 0.1,
                "bmi": 20 + person % 15, "glucose": 85 + person % 70,
                "glucose_context": "fasting", "condition_count": elevated,
                "adherence": 60 + person % 40, "disease_codes": ["EXAMPLE"],
                "station_id": "PRIVATE-STATION", "email": "do-not-use@example.test",
            })
    return result


class GroupingTests(unittest.TestCase):
    def test_aggregate_grouping_returns_no_patient_points(self):
        result = cluster_patient_groups(fixture())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(sum(row["patient_count"] or 0 for row in result["groups"]), 150)
        self.assertEqual(len(result["pca"]["explained_variance"]), 2)
        self.assertNotIn("PRIVATE-PATIENT", json.dumps(result))
        self.assertNotIn("PRIVATE-STATION", json.dumps(result))
        self.assertNotIn("do-not-use", json.dumps(result))
        self.assertTrue(all("position" in row and "profile" in row for row in result["groups"]))

    def test_group_profiles_use_one_latest_measurement_per_patient(self):
        rows = fixture(40)
        for row in rows[2::3]:
            row.update(systolic=135, diastolic=83)
        result = cluster_patient_groups(rows)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(sum(row["patient_count"] or 0 for row in result["groups"]), 40)
        for group in result["groups"]:
            if not group["suppressed"]:
                self.assertEqual(group["profile"]["systolic"]["mean"], 135)
                self.assertEqual(group["profile"]["diastolic"]["mean"], 83)

    def test_missing_other_measurements_remain_reported_as_missing(self):
        rows = fixture(40)
        for row in rows:
            row["glucose"] = None
        result = cluster_patient_groups(rows)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["missing_feature_counts"]["glucose"], 40)
        for group in result["groups"]:
            if not group["suppressed"]:
                self.assertIsNone(group["profile"]["glucose"]["mean"])
                self.assertIsNone(group["profile"]["glucose"]["observations"])

    def test_invalid_readings_and_ambiguous_dates_are_excluded(self):
        rows = fixture(40)
        for row in rows[:3]:
            row["systolic"] = None
        for row in rows[3:6]:
            row["observed_at"] = rows[3]["observed_at"]
        result = cluster_patient_groups(rows)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["eligible_patients"], 38)
        self.assertIsNone(result["excluded_rows"]["missing_or_invalid_bp"])
        self.assertIsNone(result["excluded_rows"]["ambiguous_simultaneous_rows"])

    def test_same_seed_repeats_aggregate_grouping(self):
        self.assertEqual(cluster_patient_groups(fixture(50), seed=17), cluster_patient_groups(fixture(50), seed=17))

    def test_invalid_number_of_groups_is_rejected(self):
        for n_groups in (True, 1, 7, 2.5):
            with self.subTest(n_groups=n_groups), self.assertRaises(ValueError):
                cluster_patient_groups(fixture(40), n_groups=n_groups)

    def test_grouping_handles_small_and_identical_cohorts(self):
        self.assertEqual(cluster_patient_groups(fixture(10))["status"], "insufficient_data")
        rows = fixture(40)
        template = {key: rows[0].get(key) for key in FEATURES}
        for row in rows:
            row.update(template)
        self.assertEqual(cluster_patient_groups(rows)["status"], "insufficient_data")

    def test_small_patient_counts_are_hidden(self):
        result = cluster_patient_groups(fixture(3))
        self.assertIsNone(result["eligible_patients"])


if __name__ == "__main__":
    unittest.main()
