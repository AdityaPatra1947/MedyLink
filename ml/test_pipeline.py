"""No database or external services: tests for temporal and model boundaries."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ml.pipeline import (
    FEATURES, _fit, _models, cluster_patient_groups, make_splits, patient_weights,
    predict_summary, prepare_pairs, train_and_evaluate, training_weights,
)


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


class ChronologyTests(unittest.TestCase):
    def test_future_reading_is_target_not_feature(self):
        rows = fixture(1)
        rows[0]["systolic"] = 110
        rows[1]["systolic"] = 150
        x, y, groups, info = prepare_pairs(rows)
        self.assertEqual(x[0, FEATURES.index("systolic")], 110)
        self.assertEqual(y.tolist(), [1, 0])
        self.assertEqual(info["eligible_patients"], 1)
        self.assertNotIn("PRIVATE", str(x.tolist()))
        self.assertEqual(len(groups), 2)

    def test_condition_filter_applies_to_index_not_next_visit(self):
        rows = fixture(1)
        rows[0].update(eligible_index=True, systolic=110)
        rows[1].update(eligible_index=False, systolic=150)
        rows[2].update(eligible_index=True, systolic=110)
        x, y, _, info = prepare_pairs(rows)
        self.assertEqual(len(x), 1)
        self.assertEqual(y.tolist(), [1])
        self.assertEqual(info["excluded_pairs"]["index_outside_selected_condition"], 1)

    def test_missing_or_backfilled_middle_visit_does_not_bridge(self):
        for change in ({"systolic": None}, {"available_at": "2026-04-01T00:00:00Z"}):
            rows = fixture(1)
            rows[1].update(change)
            x, _, _, info = prepare_pairs(rows)
            self.assertEqual(len(x), 0)
            self.assertEqual(sum(info["excluded_pairs"].values()), 2)

    def test_simultaneous_observation_is_a_barrier(self):
        rows = fixture(1)
        rows.append(dict(rows[1], systolic=180))
        x, _, _, info = prepare_pairs(rows)
        self.assertEqual(len(x), 0)
        self.assertEqual(info["excluded_rows"]["ambiguous_simultaneous_rows"], 2)

    def test_patient_groups_are_disjoint_in_every_split(self):
        _, y, groups, _ = prepare_pairs(fixture())
        train, test, folds = make_splits(y, groups)
        self.assertFalse(set(groups[train]) & set(groups[test]))
        for a, b in folds:
            self.assertFalse(set(groups[a]) & set(groups[b]))
            self.assertFalse(set(groups[b]) & set(groups[test]))
            self.assertEqual(set(y[a]), {0, 1})
            self.assertEqual(set(y[b]), {0, 1})

    def test_equal_total_weight_per_patient(self):
        groups = np.asarray(["a", "a", "a", "b", "c", "c"])
        weights = patient_weights(groups)
        totals = [weights[groups == person].sum() for person in ("a", "b", "c")]
        self.assertTrue(np.allclose(totals, totals[0]))

    def test_training_class_balance_uses_only_supplied_training_rows(self):
        y = np.asarray([0, 0, 0, 0, 1])
        groups = np.asarray(["a", "a", "b", "c", "d"])
        weights = training_weights(y, groups)
        self.assertAlmostEqual(weights[y == 0].sum(), weights[y == 1].sum())
        self.assertAlmostEqual(weights[0] + weights[1], weights[2])
        # Evaluation retains the actual outcome distribution rather than
        # pretending positives and negatives were equally common.
        evaluation = patient_weights(groups)
        self.assertGreater(evaluation[y == 0].sum(), evaluation[y == 1].sum())

    def test_imputation_is_fitted_from_training_rows_only(self):
        x, y, groups, _ = prepare_pairs(fixture())
        train, test, _ = make_splits(y, groups)
        column = FEATURES.index("glucose")
        x[test, column] = 99999
        expected = float(np.median(np.asarray(x[train, column], dtype=float)))
        fitted = _fit(_models(17)[0][2], x[train], y[train], groups[train])
        imputer = fitted.named_steps["preprocess"].named_transformers_["numeric"].named_steps["missing"]
        self.assertEqual(imputer.statistics_[column], expected)


class TrainingTests(unittest.TestCase):
    def test_insufficient_data_does_not_create_usable_model(self):
        with tempfile.TemporaryDirectory() as directory:
            result = train_and_evaluate(fixture(10), directory)
            self.assertEqual(result["status"], "insufficient_data")
            self.assertFalse((Path(directory) / "model_bundle.joblib").exists())
            self.assertTrue((Path(directory) / "evaluation.json").exists())

    def test_four_shared_comparisons_private_artifact_and_honest_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            result = train_and_evaluate(fixture(), directory)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(result["models"]), 4)
            self.assertEqual(len(result["baselines"]), 2)
            self.assertEqual(result["split"]["patient_overlap"], 0)
            self.assertEqual(len({model["holdout"]["examples"] for model in result["models"]}), 1)
            self.assertTrue(all(len(model["cv"]["folds"]) == 3 for model in result["models"]))
            expected = max(result["models"], key=lambda row: (row["cv"]["mean"]["macro_f1"], row["cv"]["mean"]["recall"]))
            self.assertEqual(result["selection"]["model_id"], expected["id"])
            self.assertTrue(result["feature_importance"])
            # Carry-forward is perfect on this fixture, so even a perfect fitted
            # classifier must fail the predeclared baseline-improvement gate.
            self.assertFalse(result["selection"]["prediction_enabled"])
            summary = predict_summary(fixture(), directory)
            self.assertIsNone(summary["counts"])
            text = json.dumps(result)
            self.assertNotIn("PRIVATE-PATIENT", text)
            self.assertNotIn("do-not-use", text)
            self.assertNotIn("PRIVATE-STATION", text)
            self.assertTrue((Path(directory) / "model_bundle.joblib").exists())

    def test_aggregate_grouping_returns_no_patient_points(self):
        result = cluster_patient_groups(fixture())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(sum(row["patient_count"] or 0 for row in result["groups"]), 150)
        self.assertEqual(len(result["pca"]["explained_variance"]), 2)
        self.assertNotIn("PRIVATE-PATIENT", json.dumps(result))
        self.assertTrue(all("position" in row and "profile" in row for row in result["groups"]))

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
        with tempfile.TemporaryDirectory() as directory:
            report = train_and_evaluate(fixture(3), directory)
            self.assertIsNone(report["data"]["eligible_patients"])
            self.assertTrue(report["data"]["small_counts_suppressed"])


if __name__ == "__main__":
    unittest.main()
