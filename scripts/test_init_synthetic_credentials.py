"""File-only tests; never use an application's database or existing credentials."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("credential_init", Path(__file__).with_name("init-synthetic-credentials.py"))
credential_init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credential_init)


class CredentialInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "data/synthetic/example/dataset.json"
        self.data = {
            "metadata": {"synthetic": True, "schema_version": 1, "dataset_id": "example"},
            "providers": [{"source_id": "ADMIN001", "user": {"role": "admin", "name": "Demo Admin", "email": "admin@example.test"}}],
            "patients": [{"source_id": "PAT001", "user": {"name": "Demo Patient", "email": "patient@example.test"}}],
        }
        self.write_fixture()

    def write_fixture(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        manifest = {"synthetic": True, "dataset_id": "example", "files": {"dataset.json": {"sha256": hashlib.sha256(self.path.read_bytes()).hexdigest()}}}
        self.path.with_name("manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_private_output_matches_identities_with_unique_random_passwords(self):
        destination, count = credential_init.create_credentials(self.root, self.path)
        self.assertEqual(destination, self.root / ".local/synthetic/example/credentials.json")
        self.assertEqual(count, 2)
        result = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(result["dataset_id"], "example")
        self.assertTrue(result["synthetic"])
        self.assertEqual([row["source_id"] for row in result["accounts"]], ["ADMIN001", "PAT001"])
        self.assertEqual([row["role"] for row in result["accounts"]], ["admin", "patient"])
        self.assertEqual(len({row["password"] for row in result["accounts"]}), 2)
        self.assertTrue(all(len(row["password"]) >= 30 for row in result["accounts"]))

    def test_refuses_to_replace_existing_credentials(self):
        destination, _ = credential_init.create_credentials(self.root, self.path)
        before = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            credential_init.create_credentials(self.root, self.path)
        self.assertEqual(destination.read_bytes(), before)

    def test_refuses_nonsynthetic_data_without_output(self):
        self.data["metadata"]["synthetic"] = False
        self.write_fixture()
        with self.assertRaises(ValueError):
            credential_init.create_credentials(self.root, self.path)
        self.assertFalse((self.root / ".local").exists())

    def test_refuses_duplicate_identity_without_output(self):
        self.data["patients"][0]["user"]["email"] = "ADMIN@example.test"
        self.write_fixture()
        with self.assertRaises(ValueError):
            credential_init.create_credentials(self.root, self.path)
        self.assertFalse((self.root / ".local").exists())

    def test_refuses_modified_fixture(self):
        self.path.write_text(self.path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaises(ValueError):
            credential_init.create_credentials(self.root, self.path)

    def test_refuses_dataset_outside_public_fixtures(self):
        with self.assertRaises(ValueError):
            credential_init.create_credentials(self.root, self.root / "unrelated.json")

    def test_refuses_path_traversal_dataset_id(self):
        self.data["metadata"]["dataset_id"] = "../../elsewhere"
        self.write_fixture()
        with self.assertRaises(ValueError):
            credential_init.create_credentials(self.root, self.path)


if __name__ == "__main__":
    unittest.main()
