"""Export the runtime lock for SAM, or fail if its checked-in export is stale."""

import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXPORT_ARGS = [
    "uv", "export", "--locked", "--no-default-groups", "--no-emit-project",
    "--no-annotate", "--no-header", "--format", "requirements.txt",
]


def exported_requirements(root: Path = ROOT) -> str:
    return subprocess.check_output(EXPORT_ARGS, cwd=root, text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Update src/requirements.txt")
    args = parser.parse_args()
    expected = exported_requirements()
    target = ROOT / "src" / "requirements.txt"
    if args.write:
        target.write_text(expected, encoding="utf-8")
    elif target.read_text(encoding="utf-8") != expected:
        raise SystemExit("Stale SAM requirements: run python scripts/export_requirements.py --write")
    print("SAM requirements match uv.lock")


if __name__ == "__main__":
    main()
