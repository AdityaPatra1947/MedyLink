"""Create private, fresh demo credentials for a published synthetic fixture.

This standard-library helper never connects to a database or resets accounts.
Existing credential files are never replaced, including after a failed import.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = "data/synthetic/mumbai_stations_v1/dataset.json"


def create_credentials(root: Path, dataset_path: Path) -> tuple[Path, int]:
    root = root.resolve()
    dataset_path = dataset_path.resolve()
    if not dataset_path.is_relative_to(root / "data" / "synthetic"):
        raise ValueError("Choose a fixture inside data/synthetic.")
    raw = dataset_path.read_bytes()
    dataset = json.loads(raw)
    manifest = json.loads((dataset_path.parent / "manifest.json").read_text(encoding="utf-8"))
    metadata = dataset.get("metadata", {})
    dataset_id = metadata.get("dataset_id", "")
    if (metadata.get("synthetic") is not True or metadata.get("schema_version") != 1
            or not isinstance(dataset_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_]{1,80}", dataset_id)):
        raise ValueError("The fixture must identify a version-one synthetic dataset.")
    expected = manifest.get("files", {}).get(dataset_path.name, {}).get("sha256")
    if (manifest.get("synthetic") is not True or manifest.get("dataset_id") != dataset_id
            or expected != hashlib.sha256(raw).hexdigest()):
        raise ValueError("The fixture does not match its synthetic manifest.")
    accounts, sources, emails, passwords = [], set(), set(), set()
    for collection, allowed_roles in (("providers", {"doctor", "pharmacist", "admin"}), ("patients", {"patient"})):
        entities = dataset.get(collection)
        if not isinstance(entities, list) or not entities:
            raise ValueError("Both provider and patient fixture collections are required.")
        for entity in entities:
            user = entity.get("user", {})
            source = entity.get("source_id", "")
            email, name = user.get("email", ""), user.get("name", "")
            role = user.get("role", "patient")
            if (not isinstance(source, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", source)
                    or source in sources or not isinstance(email, str) or "@" not in email
                    or email.lower() in emails or not isinstance(name, str) or not name.strip()
                    or role not in allowed_roles):
                raise ValueError("The fixture contains invalid or duplicate account identities.")
            password = "Demo!" + secrets.token_urlsafe(24)
            while password in passwords:
                password = "Demo!" + secrets.token_urlsafe(24)
            accounts.append({"source_id": source, "role": role, "name": name, "email": email, "password": password})
            sources.add(source)
            emails.add(email.lower())
            passwords.add(password)
    destination = root / ".local" / "synthetic" / dataset_id / "credentials.json"
    if not destination.resolve().is_relative_to(root / ".local"):
        raise ValueError("The private credentials path must remain inside this checkout's .local directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.resolve().is_relative_to(root / ".local"):
        raise ValueError("The private credentials path must remain inside this checkout's .local directory.")
    payload = {"dataset_id": dataset_id, "synthetic": True,
               "warning": "TEST ONLY. Import into an empty dedicated synthetic database. Never reuse these passwords.",
               "accounts": accounts}
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # O_EXCL protects existing secrets even if another process creates the file.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination, len(accounts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / DEFAULT_DATASET)
    args = parser.parse_args()
    try:
        destination, count = create_credentials(ROOT, args.dataset)
    except FileExistsError:
        parser.exit(1, "Credentials already exist; nothing was replaced. Keep them with the matching imported database.\n")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        parser.exit(1, "Could not create credentials. Check the synthetic fixture, its manifest and the private output path.\n")
    print(f"Created private credentials for {count} fictional accounts: {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
