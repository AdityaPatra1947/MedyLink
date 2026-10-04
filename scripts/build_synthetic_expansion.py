"""Build the public 3,000-patient expansion without Django or a database."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from analytics.synthetic_fixture import DEFAULT_DIRECTORY, FixtureError, build_fixture  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    try:
        manifest = build_fixture(args.output)
    except FixtureError as exc:
        parser.error(str(exc))
    print(json.dumps({"fixture_id": manifest["fixture_id"], "synthetic": True,
                      "counts": manifest["counts"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
