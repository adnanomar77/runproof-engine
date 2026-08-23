from __future__ import annotations

import json
from pathlib import Path

from runproof_engine import format_traceparent, parse_traceparent, verified


def test_traceparent_round_trip_and_nested_spans(tmp_path: Path) -> None:
    trace_id = "0123456789abcdef0123456789abcdef"
    span_id = "0123456789abcdef"
    header = format_traceparent(trace_id, span_id, 1)
    assert parse_traceparent(header) == (trace_id, span_id, 1)

    with verified("distributed-tracing", root=tmp_path / "runs") as run:
        with run.span("parent", attributes={"service.name": "producer"}) as parent:
            with run.span("child", attributes={"service.name": "worker"}) as child:
                child.set_attribute("runproof.test", True)
            assert child.parent_span_id == parent.span_id
        traceparent = run.traceparent()

    spans = json.loads((run.result.artifact_dir / "execution" / "spans.json").read_text(encoding="utf-8"))
    assert len(spans) == 2
    assert {span["name"] for span in spans} == {"parent", "child"}
    assert any(span["parent_span_id"] == parent.span_id for span in spans if span["name"] == "child")
    assert traceparent.startswith("00-")
    assert run.result.status == "verified"
