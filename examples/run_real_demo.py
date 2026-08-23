from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from runproof_engine import verified


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def profile_document(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    words = text.split()
    headings = [line for line in lines if line.startswith("#")]
    return {
        "characters": len(text),
        "lines": len(lines),
        "words": len(words),
        "headings": len(headings),
    }


if len(sys.argv) != 2:
    raise SystemExit("usage: python run_real_demo.py path/to/real-file")

source = Path(sys.argv[1]).expanduser().resolve()
with verified("real_file_profile", root="demo-runs", copy_inputs=True) as run:
    path = run.input(source, name="real_source")
    text = run.step("read_real_file", read_text, path)
    profile = run.step("profile_real_file", profile_document, text)
    run.assert_true(profile["lines"] > 0, "the real file must contain at least one line")
    run.output("profile.json", profile)

print(json.dumps({
    "status": run.result.status,
    "artifact_dir": str(run.result.artifact_dir),
    "profile": profile,
}, indent=2, ensure_ascii=False))
