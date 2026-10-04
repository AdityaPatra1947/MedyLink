"""Train disease classifiers from a private synthetic export; never queries a database."""

import argparse
import json
from pathlib import Path

from .disease_pipeline import DEFAULT_SEED, train_and_evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Private JSON list of approved synthetic visit snapshots.")
    parser.add_argument("--output", type=Path, required=True, help="New private artifact directory, outside the web root.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--task", choices=["disease"], default="disease", help="Disease classification is the supported training task.")
    args = parser.parse_args()
    if args.input.stat().st_size > 50 * 1024 * 1024:
        parser.error("The private export exceeds 50 MiB.")
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) > 50000:
        parser.error("The input must contain a list of at most 50,000 snapshots.")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Choose a new empty output directory so an earlier evaluation is preserved.")
    report = train_and_evaluate(rows, args.output, seed=args.seed)
    print(json.dumps({"status": report["status"], "selection": report["selection"], "reason": report.get("reason"), "evaluation_file": str(args.output / "evaluation.json")}, indent=2))


if __name__ == "__main__":
    main()
