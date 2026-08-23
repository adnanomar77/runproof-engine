import sys
from pathlib import Path

import pytest

from runproof_engine import auto_run, load_run
from runproof_engine.utils import read_json


def add_one(value: int) -> int:
    return value + 1


def test_auto_run_records_python_events_and_verifies(tmp_path: Path) -> None:
    with auto_run(
        "automatic-trace",
        root=tmp_path,
        backend="trace",
        include_paths=[Path(__file__).parent],
    ) as run:
        result = run.step("add-one", add_one, 41)
        run.output("result.json", {"value": result})

    artifact = run.result.artifact_dir
    events = read_json(artifact / "execution" / "trace.json")
    assert run.result.status == "verified"
    assert any(event["event"] == "observer_started" for event in events)
    assert any(
        event["event"] == "python_call"
        and event["payload"].get("function") == "add_one"
        for event in events
    )
    assert load_run(artifact).verify_integrity().status == "verified"


def test_auto_run_uses_monitoring_when_requested(tmp_path: Path) -> None:
    if not hasattr(sys, "monitoring"):
        pytest.skip("sys.monitoring requires Python 3.12+")

    with auto_run(
        "automatic-monitoring",
        root=tmp_path,
        backend="monitoring",
        include_paths=[Path(__file__).parent],
    ) as run:
        run.step("add-one", add_one, 1)
        Path(__file__).read_text(encoding="utf-8")

    events = read_json(run.result.artifact_dir / "execution" / "trace.json")
    started = [event for event in events if event["event"] == "observer_started"]
    assert started and started[0]["payload"]["backend"] == "sys.monitoring"
    assert any(event["event"] == "python_call" for event in events)
    assert any(
        event["event"] == "runtime_audit"
        and event["payload"].get("name") == "open"
        for event in events
    )
