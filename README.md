# RunProof

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

`strict` replay uses the captured input when it is available and checks whether the new execution remains comparable. A fresh run can use current inputs and can be compared with a previous run to identify changes.

## Statuses

- `verified`: execution completed and all declared checks passed.
- `verified_with_warnings`: execution completed but comparability or external-source evidence is limited.
- `failed`: execution or a required check failed.
- `blocked`: a declared policy prevented a sensitive action.
- `non_reproducible`: replay was attempted but did not match the captured run.

## Privacy and real data

RunProof records metadata and hashes by default. Full input copying is opt-in. Secrets are redacted from environment snapshots and trace values. External adapters must provide privacy-safe request metadata instead of storing credentials or raw authorization headers.

## Project status

The current repository implements the local core: run lifecycle, file fingerprints, JSON-safe artifacts, step tracing, assertions, replay, and explainable diffs. Optional integrations are intentionally separated from the core so the library remains useful without a cloud account or a specific AI provider.

## License

Apache-2.0. See `LICENSE`.
