# RunProof architecture

RunProof is intentionally local-first and provider-neutral. The core package has five boundaries.

## Run lifecycle

`RunContext` owns one named execution. It creates an artifact directory, captures a start and finish event, owns the declared input and output records, and writes a manifest at the end. The context manager does not install packages, publish files, or execute shell commands by itself.

## Evidence capture

The evidence layer calculates SHA-256 fingerprints, bounded summaries, tabular metadata for CSV and JSONL, function source fingerprints where available, and a snapshot of the Python environment. Full input copying is explicit. Values in traces are bounded and likely secret keys are redacted.

## Checks

Checks are explicit objects, not a claim that the entire result is scientifically true. The first core checks are boolean assertions, required-column checks, non-negative checks, and output-file checks. Integrations can add domain-specific checks later.

## Policy boundary

Sensitive actions are named actions. The default policy allows reading, writing an artifact, and executing declared Python. Network, upload, publish, shell, deletion, and package installation require explicit approval or can be denied. The core request adapter authorizes before opening a URL.

## Replay and diff

`LoadedRun.verify_integrity()` checks recorded inputs, outputs, and the artifact integrity manifest. `replay()` is deliberately honest: without a user-provided runner it verifies readiness but does not pretend it can reconstruct arbitrary Python state. `RunDiff` compares inputs, step status and output fingerprints, output artifacts, checks, and environment packages, then renders evidence-backed explanations.

## Artifact layout

```text
<root>/<run-name>/<run-id>/
  manifest.json
  integrity.json
  inputs/
  outputs/
  checks/results.json
  execution/trace.json
  execution/steps.json
  execution/outputs.json
  environment/snapshot.json
```

## Security posture

RunProof is not a sandbox. It records and gates declared operations, but a Python process still has the permissions of its operating system user. Applications that run untrusted generated code must execute it in a separate sandbox or worker with operating-system restrictions. The core package does not claim to provide that isolation.

## Extensibility

Adapters for pandas, polars, SQL, OpenTelemetry, OpenLineage, MCP, cloud object storage, and AI providers should depend on the stable public contracts rather than modify the manifest shape ad hoc. Every adapter must state which raw values it stores, which secrets it redacts, and whether its source can be replayed.
