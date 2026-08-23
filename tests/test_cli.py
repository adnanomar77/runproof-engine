from __future__ import annotations

import json
from pathlib import Path

from runproof_engine import verified
from runproof_engine.cli import main


def test_cli_inspect_and_verify(tmp_path: Path, capsys) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello\n", encoding="utf-8")
    with verified("cli_run", root=tmp_path / "runs") as run:
        run.input(source, name="input")
        run.output("result.json", {"ok": True})
    artifact = run.result.artifact_dir

    assert main(["inspect", str(artifact)]) == 0
    assert "status: verified" in capsys.readouterr().out
    assert main(["verify", str(artifact), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "verified"
