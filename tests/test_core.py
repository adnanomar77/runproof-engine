from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import runproof_engine
from runproof_engine import PolicyDenied, RunProofError, load_run, verified


def multiply(value: int, factor: int = 2) -> int:
    return value * factor


def make_run(root: Path, input_path: Path, value: int) -> Path:
    with verified("calculation", root=root, copy_inputs=True) as run:
        run.input(input_path, name="source")
        result = run.step("multiply", multiply, value, factor=2)
        run.assert_true(result >= 0, "result must be non-negative")
        run.output("result.json", {"value": result})
    return run.result.artifact_dir


def test_package_version_matches_project_metadata() -> None:
    project_text = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(r'^version = "([^"]+)"$', project_text, re.MULTILINE)
    assert project_version is not None
    assert runproof_engine.__version__ == project_version.group(1)


def test_run_records_real_input_steps_output_and_checks(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("real input\n", encoding="utf-8")
    artifact = make_run(tmp_path / "runs", source, 21)

    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run"]["status"] == "verified"
    assert manifest["inputs"][0]["name"] == "source"
    assert len(manifest["inputs"][0]["sha256"]) == 64
    assert manifest["steps"][0]["name"] == "multiply"
    assert manifest["steps"][0]["status"] == "completed"
    assert manifest["outputs"][0]["sha256"]
    assert manifest["checks"][0]["passed"] is True
    assert (artifact / "inputs" / "source.txt").is_file()
    assert json.loads((artifact / "outputs" / "result.json").read_text(encoding="utf-8"))["value"] == 42

    loaded = load_run(artifact)
    assert loaded.verify_integrity().status == "verified"
    assert loaded.replay(mode="strict").status == "replay_ready"


def test_relative_root_is_resolved_and_outputs_are_verifiable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with verified("relative_root", root="runs") as run:
        run.output("result.json", {"ok": True})
    assert run.result.artifact_dir.is_absolute()
    assert load_run(run.result.artifact_dir).verify_integrity().status == "verified"


def test_captured_input_can_verify_after_original_is_removed(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("captured\n", encoding="utf-8")
    artifact = make_run(tmp_path / "runs", source, 5)
    source.unlink()
    report = load_run(artifact).verify_integrity()
    assert report.status == "verified"


def test_output_tampering_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("real input\n", encoding="utf-8")
    artifact = make_run(tmp_path / "runs", source, 10)
    (artifact / "outputs" / "result.json").write_text('{"value": 999}\n', encoding="utf-8")
    report = load_run(artifact).verify_integrity()
    assert report.status == "non_reproducible"
    assert any("artifact changed" in reason for reason in report.reasons)


def test_csv_input_metadata_is_captured(tmp_path: Path) -> None:
    source = tmp_path / "sales.csv"
    source.write_text("region,amount\neast,10\nwest,20\n", encoding="utf-8")
    with verified("csv_run", root=tmp_path / "runs") as run:
        run.input(source, name="sales")
        run.external_call(
            "exchange_rate",
            provider="rates.example",
            request={"base": "USD", "api_key": "should-not-be-kept"},
            response={"rate": 1.0},
            status_code=200,
            approved=True,
        )
    manifest = json.loads((run.result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    source_record = manifest["inputs"][0]
    assert source_record["rows"] == 2
    assert source_record["columns"] == ["region", "amount"]
    trace = json.loads((run.result.artifact_dir / "execution" / "trace.json").read_text(encoding="utf-8"))
    external_events = [event for event in trace if event["event"] == "external_call"]
    assert external_events
    assert "should-not-be-kept" not in json.dumps(external_events)


def test_integrity_detects_changed_real_input(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("version one\n", encoding="utf-8")
    artifact = make_run(tmp_path / "runs", source, 3)
    source.write_text("version two\n", encoding="utf-8")

    report = load_run(artifact).verify_integrity()
    assert report.status == "non_reproducible"
    assert any("input changed" in reason for reason in report.reasons)


def test_explainable_diff_identifies_input_and_output_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("one\n", encoding="utf-8")
    first = make_run(tmp_path / "runs", source, 3)
    source.write_text("two\n", encoding="utf-8")
    second = make_run(tmp_path / "runs", source, 4)

    comparison = load_run(first).diff(second)
    assert not comparison.identical
    areas = {difference.area for difference in comparison.differences}
    assert "inputs" in areas
    assert "steps" in areas
    assert "outputs" in areas
    rendered = comparison.render()
    assert "input content changed" in rendered
    assert "step output changed" in rendered


def test_policy_blocks_sensitive_action_and_preserves_artifact(tmp_path: Path) -> None:
    run = verified("blocked", root=tmp_path / "runs")
    with pytest.raises(PolicyDenied), run:
        run.authorize("upload", target="https://example.invalid", approved=False)

    artifact = run.result.artifact_dir
    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run"]["status"] == "blocked"
    assert any(event["event"] == "action_blocked" for event in json.loads((artifact / "execution" / "trace.json").read_text(encoding="utf-8")))


def test_external_boundary_is_reported_without_false_verification(tmp_path: Path) -> None:
    with verified("boundary", root=tmp_path / "runs") as run:
        run.boundary(
            "external_service",
            target="service.example",
            reason="service state was not captured",
            replay="requires_live_service",
        )
    assert run.result.status == "verified_with_boundaries"
    manifest = json.loads((run.result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["boundaries"][0]["kind"] == "external_service"


def test_explicit_approval_is_recorded(tmp_path: Path) -> None:
    with verified("approved", root=tmp_path / "runs") as run:
        decision = run.authorize("upload", target="https://example.invalid", approved=True)
        assert decision["approved"] is True
    assert run.result.status == "verified"


def test_artifact_path_cannot_escape_run_directory(tmp_path: Path) -> None:
    run = verified("escape", root=tmp_path / "runs")
    with pytest.raises(RunProofError), run:
        run.output("../outside.json", {"unsafe": True})
