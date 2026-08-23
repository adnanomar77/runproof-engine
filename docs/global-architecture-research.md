
## Additional findings

Python 3.12 introduced `sys.monitoring`, a dedicated execution monitoring namespace with tool identifiers and selectable callbacks. The official documentation lists events such as calls, returns, lines, branches, raises, and C-level returns/raises. This should be the preferred low-overhead execution hook on Python versions that support it, with `sys.settrace()` as a compatibility fallback for older versions and features not covered by monitoring.

PEP 751 is a final Python packaging standard-track proposal for a file format that records dependencies for installation reproducibility. Its model includes locked package versions, environment markers, Python requirements, source/archive locations, hashes, wheels, and attestation identities. RunProof should record and consume lock metadata when present, while retaining compatibility with requirements files and package metadata when no lock exists. A lock file can make environment reconstruction more precise, but cannot by itself reproduce operating-system, hardware, external-service, or data-state effects.

## Draft layered architecture

1. **Launcher and context layer**: `runproof run module:callable`, `python -m runproof`, and an embeddable context API; creates run IDs, policy, redaction, and evidence storage.
2. **Runtime observation layer**: `sys.monitoring` on Python >= 3.12, `sys.settrace` fallback, `sys.addaudithook` for visible runtime actions, and thread/process propagation.
3. **Boundary adapters**: monkey-patch or instrumentation adapters for HTTP, database, filesystem, subprocess, dataframe, notebook, queue, cloud, and ML libraries.
4. **Evidence graph**: content-addressed blobs plus a normalized event/provenance graph connecting inputs, steps, environment, external calls, outputs, and checks.
5. **Verification and replay layer**: integrity verification, replay contract, environment/lock comparison, deterministic replay where an adapter can provide it, and boundary-aware statuses.
6. **Explainability layer**: causal candidate analysis and human-readable diff based on changed evidence, not only aggregate hashes.
7. **Interoperability layer**: OpenTelemetry export for traces, JSON/JSONL artifact format, CLI, Python API, and plugin SDK.
