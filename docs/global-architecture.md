# RunProof Global Architecture

## Purpose

RunProof is an evidence engine for Python executions. Its promise is to capture and explain observable computation with the least possible manual annotation. It is not a sandbox, a universal debugger, or a guarantee that arbitrary external reality can be replayed exactly.

## Public surfaces

The product should expose four compatible entry points:

```bash
runproof run mypackage.jobs:train --arg-config config.json
python -m runproof myscript.py
```

```python
from runproof_engine import auto_run, verified

with auto_run("training-job") as run:
    result = train(dataset)
```

```python
from runproof_engine import load_run

report = load_run("runs/training-job/<run-id>").verify_integrity()
```

The existing `verified(...)` context remains the explicit, low-dependency API. `auto_run(...)` becomes the recommended default for whole-process capture.

## Runtime layers

### 1. Launcher and lifecycle

The launcher creates a run ID, captures command-line arguments, working directory, selected environment variables, Python version, package metadata, source revision, policy, and capture configuration. It installs hooks before importing the target module where possible and propagates a run context to child processes.

### 2. Execution observation

On Python 3.12 and newer, use `sys.monitoring` with selective events and sampling to reduce overhead. On older supported versions, use `sys.settrace` with thread registration and a configurable scope. Use `sys.addaudithook` for observable runtime actions such as file, process, import, and network-related events, while documenting that audit hooks are not a sandbox.

The baseline observer records event identity, parent span, source location, duration, exception outcome, and bounded metadata. It does not serialize every local variable or every line by default because that would create unacceptable overhead, privacy risk, and artifact volume.

### 3. Boundary adapters

Adapters intercept high-value boundaries rather than every internal function: filesystem, HTTP clients, database drivers, subprocesses, queues, dataframe operations, notebooks, object stores, ML frameworks, and agent/tool calls. Every adapter declares capture level, replay strategy, redaction rules, and unsupported cases.

Adapters must be optional extras, independently versioned where practical, and tested against a compatibility matrix. OpenTelemetry span context can be accepted/exported for interoperability, but RunProof retains its own evidence records and hashes.

### 4. Evidence model

Store immutable, content-addressed blobs for captured inputs and outputs, a normalized event log, and a provenance graph. Each node has a stable ID, type, timestamp, source, digest, size/summary, and sensitivity classification. Edges represent read, wrote, called, derived-from, imported, spawned, and checked relationships.

The manifest contains the schema version, capture configuration, package/lock information, source fingerprints, policy decisions, boundary declarations, and integrity records. Sensitive values are redacted or excluded by default; a digest can remain even when content is unavailable.

### 5. Verification states

Verification must be evidence-boundary aware. `verified` means the recorded artifact is intact and all declared checks passed. `verified_with_boundaries` means integrity is intact but one or more relevant effects are external, opaque, or non-deterministic. `non_reproducible` means required evidence differs or is missing. `blocked` and `failed` remain distinct states.

### 6. Replay engine

Replay has two modes. In deterministic mode, adapters substitute captured responses and inputs only where the user explicitly enables it. In live mode, the runner re-executes against current dependencies and external systems under policy control. Both modes produce a new RunProof artifact and compare it with the source run. No arbitrary Python program is silently re-executed without a user-supplied entry point and approval for side effects.

### 7. Explainable Diff

Compare runs at several levels: source and package fingerprints, dependency lock data, environment, event graph, inputs, external calls, checks, and outputs. The engine generates candidate explanations such as “output changed after input digest changed,” “same input but dependency version changed,” or “external response differs.” It must label explanations as observed evidence or inference and must not claim causality when the graph cannot support it.

### 8. Storage and interoperability

The local artifact format remains the source of truth. Add a content-addressed store abstraction for local directories and later object storage. Support JSON/JSONL export, a stable schema, and OpenTelemetry trace export. Cloud synchronization is opt-in and policy-gated; the core library remains usable offline.

## Security and trust boundaries

RunProof must never imply isolation. A traced process has the permissions of its user, Python hooks can be bypassed by hostile/native code, and external services cannot be made deterministic by hashing their responses. Redaction, allowlists, approval gates, encrypted optional stores, external integrity digests, and explicit boundary statuses are required.

## Compatibility strategy

Support CPython 3.10+ initially. Use feature detection for `sys.monitoring`. Test CPython 3.10, 3.11, 3.12, 3.13, and 3.14 across Linux, macOS, and Windows in CI. Treat PyPy and alternative runtimes as a separately declared compatibility target rather than assuming CPython hooks behave identically.

## Release gates

A release is not publishable until unit tests, integration tests, real subprocess tests, adapter contract tests, security/redaction tests, performance benchmarks, package build checks, clean-environment installation, documentation examples, and an end-to-end replay/diff scenario pass. The version must be sourced consistently and release publishing should use repository-scoped trusted publishing rather than a broad account token.
