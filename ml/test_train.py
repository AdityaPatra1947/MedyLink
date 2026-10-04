"""CLI routing checks; model fitting is mocked and no database is accessed."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ml
from ml import disease_pipeline, train


class DiseaseTrainingCommandTests(unittest.TestCase):
    def test_package_training_and_prediction_exports_use_disease_task(self):
        self.assertIs(ml.train_and_evaluate, disease_pipeline.train_and_evaluate)
        self.assertIs(ml.predict_summary, disease_pipeline.predict_summary)

    def test_default_command_calls_disease_pipeline_with_its_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.json", Path(directory) / "model"
            source.write_text("[]", encoding="utf-8")
            report = {"status": "insufficient_data", "selection": None, "reason": "More patients are needed."}
            printed = io.StringIO()
            with patch("sys.argv", ["ml.train", "--input", str(source), "--output", str(output)]), patch(
                "ml.train.train_and_evaluate", return_value=report,
            ) as training, contextlib.redirect_stdout(printed):
                train.main()
            training.assert_called_once_with([], output, seed=disease_pipeline.DEFAULT_SEED)
            self.assertEqual(json.loads(printed.getvalue())["status"], "insufficient_data")

    def test_explicit_disease_task_and_seed_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.json", Path(directory) / "model"
            source.write_text("[]", encoding="utf-8")
            argv = ["ml.train", "--task", "disease", "--seed", "7", "--input", str(source), "--output", str(output)]
            with patch("sys.argv", argv), patch("ml.train.train_and_evaluate", return_value={"status": "completed", "selection": None}) as training, contextlib.redirect_stdout(io.StringIO()):
                train.main()
            training.assert_called_once_with([], output, seed=7)

    def test_removed_task_is_rejected_before_reading_data_or_fitting(self):
        argv = ["ml.train", "--task", "blood_pressure", "--input", "unused.json", "--output", "unused-output"]
        with patch("sys.argv", argv), patch("ml.train.train_and_evaluate") as training, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            train.main()
        self.assertEqual(error.exception.code, 2)
        training.assert_not_called()

    def test_existing_artifacts_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.json", Path(directory) / "model"
            source.write_text("[]", encoding="utf-8")
            output.mkdir()
            artifact = output / "evaluation.json"
            artifact.write_text('{"preserve":true}', encoding="utf-8")
            with patch("sys.argv", ["ml.train", "--input", str(source), "--output", str(output)]), patch(
                "ml.train.train_and_evaluate",
            ) as training, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                train.main()
            training.assert_not_called()
            self.assertEqual(artifact.read_text(encoding="utf-8"), '{"preserve":true}')


if __name__ == "__main__":
    unittest.main()
