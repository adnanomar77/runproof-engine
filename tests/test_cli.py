from __future__ import annotations

import json
from pathlib import Path

from runproof_engine import load_run, verified
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


def test_cli_run_executes_real_script(tmp_path: Path, capsys) -> None:
    script = tmp_path / "real_script.py"
    script.write_text(
        "from pathlib import Path\n"
        f"Path({str(tmp_path / 'created.txt')!r}).write_text('real output\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    root = tmp_path / "runs"

    assert main([
        "run",
        str(script),
        "--root",
        str(root),
        "--backend",
        "trace",
        "--capture-output",
        str(tmp_path / "created.txt"),
    ]) == 0
    output = capsys.readouterr().out
    artifact_line = next(line for line in output.splitlines() if line.startswith("artifact_dir: "))
    artifact = Path(artifact_line.split(": ", 1)[1])
    loaded = load_run(artifact)
    assert loaded.verify_integrity().status == "verified"
    assert (artifact / "outputs" / "auto" / "created.txt").is_file()

    replay_root = tmp_path / "replays"
    assert main([
        "replay",
        str(artifact),
        str(script),
        "--root",
        str(replay_root),
        "--backend",
        "trace",
        "--capture-output",
        str(tmp_path / "created.txt"),
    ]) == 0
    replay_output = capsys.readouterr().out
    assert "status: verified" in replay_output
    assert "compared_run_id:" in replay_output
