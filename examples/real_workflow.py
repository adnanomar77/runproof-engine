"""Run a real local-file workflow.

Usage:
    python examples/real_workflow.py path/to/your.csv

The example never creates an input dataset. It reads the file supplied by the user.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

from runproof_engine import verified


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def profile_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    columns = sorted({key for row in rows for key in row})
    missing = {column: sum(not row.get(column) for row in rows) for column in columns}
    return {"rows": len(rows), "columns": columns, "missing_values": missing}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python examples/real_workflow.py path/to/your.csv")
        return 2
    source = Path(sys.argv[1]).expanduser().resolve()
    with verified("csv_profile", root="runs", copy_inputs=False) as run:
        path = run.input(source, name="source_csv")
        rows = run.step("read_csv", read_csv, path)
        profile = run.step("profile_rows", profile_rows, rows)
        run.assert_true(profile["rows"] >= 0, "row count cannot be negative")
        run.output("profile.json", profile)
    print(run.result.summary())
    print(json.dumps(profile, indent=2, ensure_ascii=False))
    return 0 if run.result.status == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
