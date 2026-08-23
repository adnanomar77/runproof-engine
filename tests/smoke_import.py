from __future__ import annotations

import sys
from pathlib import Path

from runproof_engine import load_run, verified

root = Path(sys.argv[1])
source = root / "input.txt"
source.write_text("installed package\n", encoding="utf-8")
with verified("installed_smoke", root=root / "runs") as run:
    path = run.input(source, name="input")
    lines = run.step("read", lambda value: value.read_text(encoding="utf-8").splitlines(), path)
    run.assert_true(len(lines) == 1, "one line expected")
    run.output("summary.json", {"lines": len(lines)})

loaded = load_run(run.result.artifact_dir)
assert loaded.verify_integrity().status == "verified"
assert loaded.diff(loaded).identical
print(run.result.status)
