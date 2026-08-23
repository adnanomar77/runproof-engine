# RunProof

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22072586.svg)](https://doi.org/10.5281/zenodo.22072586)

RunProof is a Python library for recording, validating, replaying, and comparing real computational runs. It turns a Python execution into an inspectable artifact containing inputs, outputs, code references, environment metadata, checks, and an execution trace.

The distinctive feature is **Explainable Diff**: when two runs differ, RunProof compares input fingerprints, schemas, output summaries, step status, code fingerprints, and environment metadata, then reports evidence-backed causes instead of only saying that the runs are different.

## What it is

RunProof is a local-first execution record and reproducibility layer for Python workflows. It is useful for data analysis, reports, ML experiments, research software, API workflows, and any process where the result must be explained later.

RunProof is not a reverse-engineering tool, a code generator, a replacement for Git, or a guarantee that a scientific conclusion is correct. It records and validates the execution that was declared to it.

## Quick start

```python
from runproof_engine import verified


def clean_rows(rows):
    return [row for row in rows if row["amount"] >= 0]


def total(rows):
    return sum(row["amount"] for row in rows)

with verified("sales_total", root="runs") as run:
    rows = run.input("sales.json", name="sales")
    cleaned = run.step("clean_rows", clean_rows, rows)
    result = run.step("total", total, cleaned)
    run.assert_true(result >= 0, "total must be non-negative")
    run.output("total.json", {"total": result})

print(run.result.status)
print(run.result.artifact_dir)
```

This creates a run directory with a manifest, input metadata, output metadata, trace events, checks, and an environment snapshot. The input is not silently replaced by generated data. File contents are fingerprinted, while copying full inputs is explicit and configurable.

## Automatic capture

For whole-process observation, use `auto_run`. It installs a Python execution observer for the lifetime of the context. On Python 3.12 and newer it uses `sys.monitoring` when available; otherwise it falls back to `sys.settrace`. The observer records bounded call, return, and exception events without requiring every function to be wrapped manually.

```python
from pathlib import Path
from runproof_engine import auto_run

with auto_run(
    "automatic-report",
    root="runs",
    include_paths=[Path("src")],
) as run:
    report = build_report(real_input)
    run.observe(report, name="report")
    run.output("report.json", report)
```

Automatic capture is an evidence layer, not a sandbox. It does not serialize every local variable, intercept every native extension, or make external services deterministic. Use adapters or explicit `run.input`, `run.step`, and `run.external_call` calls when a boundary needs stronger evidence.

### Optional real-library adapters

When an optional dependency is installed, `auto_run` discovers and activates its adapter by default. The current adapters observe real operations through documented hooks or narrowly scoped wrappers:

| Integration | Captured evidence | Boundary behavior |
| --- | --- | --- |
| pandas | DataFrame reads/writes, summaries, file hashes | Local file outputs can be archived; in-memory and native execution remain bounded |
| Polars | DataFrame reads/writes, summaries, file hashes | Requires the optional `polars` package |
| requests | Prepared URL, redacted headers, status code | Response bodies are not consumed automatically; live network remains a boundary |
| HTTPX | Sync and async request/response hooks | Streaming bodies are not consumed automatically; live network remains a boundary |
| SQLite | SQL statements and database path | Database transaction state is a boundary; mutable files can become `non_reproducible` |
| SQLAlchemy and psycopg | Cursor statements and database dialect | Requires the optional database package and a live database policy |
| subprocess | Command summary, return code, stdout/stderr digests | Process environment and side effects remain a boundary |
| Boto3 | Service operation, redacted parameters, response summary | Cloud object/service state remains a boundary |
| Jupyter/nbclient | Notebook execution lifecycle | Kernel state and external effects remain a boundary |
| Torch and joblib | Model save/load file evidence | Device/native runtime state may remain a boundary |

The optional adapters never execute installation commands and never send captured data to RunProof services. They can be disabled or replaced by passing an explicit `adapters=` collection to `auto_run`.

## Provenance, environment, and distributed tracing

Every completed run now contains `provenance.json`, a graph connecting the run to inputs, steps, values, outputs, checks, observations, and evidence boundaries. It is available through `load_run(path).provenance` and is designed to make later diffs explainable without pretending to prove causality.

The artifact also contains `environment/environment.lock.json`. It records the interpreter, platform, and installed package versions and can be compared with `compare_environment_lock(...)`. `reconstruction_plan(...)` returns reviewable pip commands but deliberately marks them as requiring approval; RunProof never installs packages silently. Package locks do not reproduce operating-system state, hardware, external services, or changing data.

For service-to-service workflows, use `run.span(...)` and propagate `run.traceparent()`. Spans are stored in `execution/spans.json` using a dependency-free W3C traceparent-compatible format. OpenTelemetry exporters can be added as adapters without making OpenTelemetry a runtime dependency.

## Replay and comparison

```python
from runproof_engine import load_run

previous = load_run("runs/sales_total/20260823-101500-abc123")
replayed = previous.replay(mode="strict")
print(replayed.status)

comparison = previous.diff(replayed)
print(comparison.to_dict())
print(comparison.render())
```

Without a runner, `replay()` verifies the captured artifact and reports `replay_ready`; it does not silently re-execute arbitrary Python. To perform a real replay, provide a user-controlled runner that invokes the original workflow and returns the new artifact. The resulting run can then be compared with the previous run to identify evidence-backed changes.

## Statuses

- `verified`: execution completed and all declared checks passed with no recorded evidence boundary.
- `verified_with_boundaries`: execution completed and the artifact is intact, but one or more external or non-deterministic effects remain outside the captured evidence.
- `verified_with_warnings`: execution completed but comparability or external-source evidence is limited.
- `failed`: execution or a required check failed.
- `blocked`: a declared policy prevented a sensitive action.
- `non_reproducible`: replay was attempted but did not match the captured run.

## Privacy and real data

RunProof records metadata and hashes by default. Full input copying is opt-in. Secrets are redacted from environment snapshots and trace values. External adapters must provide privacy-safe request metadata instead of storing credentials or raw authorization headers.

## Project status

The current repository implements the local core, automatic observation, provenance graph, environment lock, distributed trace context, and optional real-library integrations. It remains useful without a cloud account or a specific AI provider. Automatic observation still has explicit coverage boundaries; it is not a universal sandbox or a guarantee of perfect replay for arbitrary Python.

## License

Apache-2.0. See `LICENSE`.
