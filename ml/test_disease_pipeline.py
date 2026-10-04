"""No database: tests for the synthetic disease task's evaluation boundaries."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ml.disease_pipeline import (
    CLASSES,
    FEATURES,
    SYMPTOM_FEATURES,
    _fit,
    _models,
    _public_report,
    choose_by_cv,
    make_splits,
    metrics,
    patient_weights,
    predict_summary,
    prediction_gate,
    prepare_examples,
    train_and_evaluate,
)


def fixture(patients_per_class=20, visits=2):
    """Small learnable fixture; not the application generator or medical rules."""
    rows = []
    for disease_index, disease in enumerate(CLASSES):
        for patient in range(patients_per_class):
            for visit in range(visits):
                stamp = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=30 * visit + patient)
                row = {
                    "patient_key": f"PRIVATE-{disease_index}-{patient}", "primary_disease": disease,
                    "observed_at": stamp.isoformat(), "available_at": stamp.isoformat(), "synthetic": True,
                    "age": 20 + disease_index * 6 + patient % 3, "month": 12,
                    "gender": "female" if patient % 2 else "male", "station_id": f"AREA-{patient % 4}",
                    "temperature": 36.0 + disease_index * 0.25, "systolic": 105 + disease_index * 6,
                    "diastolic": 65 + disease_index * 3, "glucose": 75 + disease_index * 12,
                    "hemoglobin": 10 + disease_index * 0.5, "spo2": 90 + disease_index,
                    "pulse": 60 + disease_index * 4, "platelets": 120000 + disease_index * 18000,
                    "diagnosis": f"LEAK-{disease}", "medications": f"LEAK-{disease}",
                    "email": "PRIVATE@example.test", "doctor_id": "PRIVATE-DOCTOR",
                }
                row.update({name: (disease_index >> (index % 4)) & 1 for index, name in enumerate(SYMPTOM_FEATURES)})
                if patient % 11 == 0:
                    row["glucose"] = None
                rows.append(row)
    return rows


class PreparationTests(unittest.TestCase):
    def test_allowlist_excludes_labels_text_ids_and_later_information(self):
        rows = fixture(1, 1)
        x, y, groups, info = prepare_examples(rows)
        self.assertEqual(x.shape, (10, len(FEATURES)))
        for key in ("primary_disease", "diagnosis", "medications", "patient_key", "doctor_id", "email", "available_at"):
            self.assertNotIn(key, FEATURES)
        self.assertNotIn("PRIVATE", str(x.tolist()))
        self.assertNotIn("LEAK", str(x.tolist()))
        self.assertEqual(set(y), set(CLASSES))
        self.assertEqual(len(set(groups)), 10)
        self.assertEqual(info["eligible_patients"], 10)
        # The untrusted supplied month cannot override visit chronology.
        self.assertEqual(set(x[:, FEATURES.index("month")]), {1.0})

    def test_backfilled_missing_dates_future_and_real_rows_are_excluded(self):
        rows = fixture(1, 1)
        rows[0]["available_at"] = "2026-01-01T00:00:00Z"
        rows[1]["available_at"] = None
        rows[2]["synthetic"] = False
        rows[3]["observed_at"] = "2999-01-01T00:00:00Z"
        _, y, _, info = prepare_examples(rows)
        self.assertEqual(len(y), 6)
        self.assertEqual(info["excluded_rows"]["available_after_visit"], 1)
        self.assertEqual(info["excluded_rows"]["invalid_or_missing_dates"], 1)
        self.assertEqual(info["excluded_rows"]["not_explicitly_synthetic"], 1)
        self.assertEqual(info["excluded_rows"]["future_visit"], 1)

    def test_ambiguous_same_visit_rows_are_not_silently_used(self):
        rows = fixture(1, 1)
        rows.append(dict(rows[0], primary_disease=CLASSES[1]))
        _, y, _, info = prepare_examples(rows)
        self.assertEqual(len(y), 9)
        self.assertEqual(info["excluded_rows"]["ambiguous_same_visit_rows"], 2)

    def test_missing_symptom_is_unknown_not_false_and_invalid_values_are_missing(self):
        rows = fixture(1, 1)
        rows[0].update(fever=None, cough=False, glucose=float("inf"), spo2=101, rash="yes")
        x, _, groups, _ = prepare_examples(rows)
        row = x[np.flatnonzero(groups == rows[0]["patient_key"])[0]]
        for name in ("fever", "glucose", "spo2", "rash"):
            self.assertTrue(np.isnan(row[FEATURES.index(name)]))
        self.assertEqual(row[FEATURES.index("cough")], 0)

    def test_unknown_or_malformed_target_is_not_inferred_from_diagnosis_text(self):
        rows = fixture(1, 1)
        rows[0]["primary_disease"] = None
        rows[1]["primary_disease"] = ["DENGUE"]
        rows[2]["primary_disease"] = "NO_RECORDED_DISEASE"
        _, y, _, info = prepare_examples(rows)
        self.assertEqual(len(y), 7)
        self.assertEqual(info["excluded_rows"]["missing_or_unknown_primary_disease"], 3)

    def test_preprocessing_learns_imputation_from_training_only(self):
        x, y, groups, _ = prepare_examples(fixture(10))
        training, holdout, _ = make_splits(y, groups)
        position = FEATURES.index("glucose")
        x[holdout, position] = 99999
        expected = np.nanmedian(np.asarray(x[training, position], dtype=float))
        fitted = _fit(_models(42)[0][2], x[training], y[training])
        numeric = fitted.named_steps["preprocess"].named_transformers_["numeric"]
        self.assertEqual(numeric.named_steps["missing"].statistics_[position], expected)
        self.assertIn("scale", numeric.named_steps)
        self.assertIn("encode", fitted.named_steps["preprocess"].named_transformers_["categorical"].named_steps)


class SplitTests(unittest.TestCase):
    def test_patient_holdout_and_every_cv_fold_are_disjoint(self):
        _, y, groups, _ = prepare_examples(fixture(15, 3))
        training, holdout, folds = make_splits(y, groups)
        self.assertEqual(len(set(groups[training])), 120)
        self.assertEqual(len(set(groups[holdout])), 30)
        self.assertEqual(len(folds), 5)
        self.assertFalse(set(groups[training]) & set(groups[holdout]))
        validation_appearances = []
        for fit, validate in folds:
            self.assertFalse(set(groups[fit]) & set(groups[validate]))
            self.assertFalse(set(groups[fit]) & set(groups[holdout]))
            self.assertFalse(set(groups[validate]) & set(groups[holdout]))
            self.assertEqual(set(groups[fit]) | set(groups[validate]), set(groups[training]))
            self.assertEqual(set(y[fit]), set(CLASSES))
            self.assertEqual(set(y[validate]), set(CLASSES))
            validation_appearances.extend(set(groups[validate]))
        self.assertEqual(len(validation_appearances), len(set(validation_appearances)))
        self.assertEqual(set(validation_appearances), set(groups[training]))

    def test_multiple_diseases_per_patient_and_input_order_remain_reproducible(self):
        rows = fixture(15, 3)
        # A different secondary visit label must not split this patient apart.
        for index, row in enumerate(rows):
            if index % 3 == 2:
                row["primary_disease"] = CLASSES[(CLASSES.index(row["primary_disease"]) + 1) % len(CLASSES)]
        _, y, groups, _ = prepare_examples(rows)
        a, b, folds = make_splits(y, groups, seed=18)
        permutation = np.random.default_rng(8).permutation(len(y))
        c, d, shuffled_folds = make_splits(y[permutation], groups[permutation], seed=18)
        self.assertEqual(set(groups[a]), set(groups[permutation][c]))
        self.assertEqual(set(groups[b]), set(groups[permutation][d]))
        for (fit, validate), (fit2, validate2) in zip(folds, shuffled_folds):
            self.assertEqual(set(groups[fit]), set(groups[permutation][fit2]))
            self.assertEqual(set(groups[validate]), set(groups[permutation][validate2]))

    def test_different_seed_changes_membership_not_coverage(self):
        _, y, groups, _ = prepare_examples(fixture())
        _, first, _ = make_splits(y, groups, 42)
        _, second, _ = make_splits(y, groups, 43)
        self.assertNotEqual(set(groups[first]), set(groups[second]))
        self.assertEqual(len(set(groups[first])), len(set(groups[second])))

    def test_repeat_visits_do_not_increase_metric_weight(self):
        groups = np.asarray(["a", "a", "a", "b", "c", "c"])
        weights = patient_weights(groups)
        self.assertEqual(weights[groups == "a"].sum(), weights[groups == "b"].sum())
        self.assertEqual(weights[groups == "b"].sum(), weights[groups == "c"].sum())


class SelectionTests(unittest.TestCase):
    def test_small_confusion_cells_are_hidden_without_hiding_the_entire_matrix(self):
        _, y, groups, data = prepare_examples(fixture(10, 1))
        predicted = y.copy()
        source = np.flatnonzero(y == CLASSES[0])[0]
        predicted[source] = CLASSES[1]
        measured = metrics(y, predicted, groups)
        public = _public_report({
            "data": data, "split": None,
            "models": [{"cv": {"folds": [measured]}, "holdout": metrics(y, predicted, groups)}],
        })
        matrix = public["models"][0]["holdout"]["confusion_matrix"]
        self.assertEqual(matrix[0][0], 9)
        self.assertIsNone(matrix[0][1])
        self.assertEqual(matrix[0][2], 0)
        self.assertEqual(matrix[1][1], 10)

    def test_winner_is_chosen_from_cv_even_when_another_has_better_holdout(self):
        models = [
            {"id": "a", "cv": {"mean": {"macro_f1": 0.80}}, "holdout": {"macro_f1": 0.95}},
            {"id": "b", "cv": {"mean": {"macro_f1": 0.81}}, "holdout": {"macro_f1": 0.65}},
        ]
        self.assertEqual(choose_by_cv(models)["id"], "b")

    def test_both_quality_thresholds_are_required(self):
        for accuracy, f1, enabled in ((0.75, 0.70, True), (0.749, 0.9, False), (0.99, 0.699, False)):
            checks, message = prediction_gate({"accuracy": accuracy, "macro_f1": f1})
            self.assertEqual(all(checks.values()), enabled)
            if not enabled:
                self.assertIn("Predictions are disabled", message)

    def test_insufficient_classes_write_report_without_leaving_stale_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "model_bundle.joblib").write_bytes(b"an older model")
            result = train_and_evaluate(fixture(3), path)
            self.assertEqual(result["status"], "insufficient_data")
            self.assertIsNone(result["selection"])
            self.assertFalse((path / "model_bundle.joblib").exists())
            self.assertTrue((path / "evaluation.json").exists())
            self.assertTrue(all(value is None for value in result["data"]["patients_per_class"].values()))
            summary = predict_summary(fixture(3), path)
            self.assertFalse(summary["prediction_enabled"])
            self.assertEqual(summary["counts"], [])


class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.rows = fixture(25)
        cls.report = train_and_evaluate(cls.rows, cls.directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_four_models_share_five_folds_and_test_patient_count(self):
        report = self.report
        self.assertEqual(report["status"], "completed")
        self.assertEqual({row["id"] for row in report["models"]}, {"logistic_regression", "decision_tree", "random_forest", "knn"})
        self.assertEqual(report["split"]["training_patients"], 200)
        self.assertEqual(report["split"]["holdout_patients"], 50)
        self.assertEqual(report["split"]["patient_overlap"], 0)
        self.assertEqual({row["holdout"]["patients"] for row in report["models"]}, {50})
        self.assertTrue(all(len(row["cv"]["folds"]) == 5 for row in report["models"]))
        best = max(report["models"], key=lambda row: row["cv"]["mean"]["macro_f1"])
        self.assertEqual(report["selection"]["model_id"], best["id"])
        self.assertEqual(report["selection"]["prediction_enabled"], best["holdout"]["accuracy"] >= .75 and best["holdout"]["macro_f1"] >= .70)

    def test_report_has_no_patient_keys_and_only_individual_small_cells_are_hidden(self):
        serialized = json.dumps(self.report)
        self.assertNotIn("PRIVATE-", serialized)
        self.assertNotIn("@example", serialized)
        self.assertNotIn("LEAK-", serialized)
        self.assertEqual(len(self.report["class_labels"]), 10)
        for model in self.report["models"]:
            for metric in model["cv"]["folds"] + [model["holdout"]]:
                matrix = metric["confusion_matrix"]
                self.assertEqual(len(matrix), 10)
                self.assertTrue(all(len(row) == 10 for row in matrix))
                self.assertTrue(all(cell is None or cell == 0 or cell >= 5 for row in matrix for cell in row))
                self.assertEqual(metric["confusion_labels"], list(CLASSES))

    def test_saved_artifacts_and_latest_per_patient_prediction(self):
        directory = Path(self.directory.name)
        self.assertTrue((directory / "model_bundle.joblib").exists())
        saved = json.loads((directory / "evaluation.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, self.report)
        self.assertEqual({item["feature"] for item in saved["feature_importance"]}, set(FEATURES))
        # Inference need not be given a diagnosis label.
        rows = [{key: value for key, value in row.items() if key != "primary_disease"} for row in self.rows]
        summary = predict_summary(rows, directory)
        self.assertEqual(summary["eligible_patients"], 250)
        self.assertNotIn("PRIVATE", json.dumps(summary))
        self.assertEqual(summary["labels"], list(CLASSES))
        self.assertIsInstance(summary["counts"], list)
        if summary["prediction_enabled"]:
            self.assertEqual({item["code"] for item in summary["counts"]}, set(CLASSES))
            self.assertTrue(all(item["label"] for item in summary["counts"]))
            self.assertEqual(sum(item["count"] or 0 for item in summary["counts"]), 250)

    def test_disabled_report_never_loads_or_uses_an_older_enabled_model(self):
        with tempfile.TemporaryDirectory() as directory:
            report = json.loads(json.dumps(self.report))
            report["selection"]["prediction_enabled"] = False
            report["selection"]["message"] = "Predictions are disabled for this test."
            (Path(directory) / "evaluation.json").write_text(json.dumps(report), encoding="utf-8")
            with patch("ml.disease_pipeline.joblib.load", side_effect=AssertionError("must not load")):
                summary = predict_summary(self.rows, directory)
            self.assertFalse(summary["prediction_enabled"])
            self.assertEqual(summary["counts"], [])


if __name__ == "__main__":
    unittest.main()
