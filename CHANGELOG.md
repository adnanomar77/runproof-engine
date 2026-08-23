# Changelog

## 0.2.0 — automatic observation and boundary-aware replay

### Added

- Added `auto_run` and `AutoCapture` for automatic Python call/return/exception observation.
- Added `sys.monitoring` support on Python 3.12+ with a `sys.settrace` fallback for Python 3.10 and 3.11.
- Added bounded runtime audit observation for selected file, process, and socket events.
- Added adapter contracts and real-library adapters for pandas, Polars, SQLite, SQLAlchemy, psycopg, requests, HTTPX, subprocess, Jupyter/nbclient, Boto3, Torch, and joblib when the optional dependencies are installed.
- Added a standard-library `urllib` adapter with URL query redaction and an HTTP/HTTPS allowlist.
- Added automatic output capture through `capture_outputs` and CLI `--capture-output`.
- Added CLI `run` for observing a complete Python script and CLI `replay` for user-controlled re-execution and comparison.
- Added provenance graphs connecting runs, inputs, steps, outputs, checks, observations, and evidence boundaries.
- Added environment lock artifacts, environment comparison, and an approval-required reconstruction plan that never installs packages silently.
- Added dependency-free W3C `traceparent`-compatible distributed tracing with parent-child spans stored in run artifacts.
- Added `verified_with_boundaries` status and explicit evidence-boundary records for databases, networks, subprocesses, notebooks, cloud services, and native runtime state.
- Extended Explainable Diff to compare observations, boundaries, execution signatures, environment metadata, and causal candidates marked as inference.
- Added Hypothesis fuzz tests, Bandit security scanning, dependency-audit and capture-performance quality gates.
- Added GitHub Actions compatibility coverage for Python 3.10–3.14 on Ubuntu, macOS, and Windows, plus package build validation.
- Added an OIDC Trusted Publishing release workflow for PyPI using the dedicated GitHub Actions `release` environment.

### Verification

- 33 local tests pass, including real local integration tests for pandas, Polars, SQLite, SQLAlchemy with SQLite, requests, HTTPX sync/async, subprocess, Jupyter/nbclient, joblib, tracing, fuzzing, and replay behavior.
- `ruff check src tests`, `compileall`, and `bandit -r src -ll` pass locally; Bandit reports `No issues identified`.
- The 0.2.0 sdist and wheel build successfully and both pass `twine check`.
- A clean virtual environment installed the built 0.2.0 wheel, imported `runproof_engine.__version__ == "0.2.0"`, and verified a smoke run against the repository's real `README.md`.
- The final public release must pass the remote CI workflow and an independent installation from PyPI before it is considered published.

### Evidence boundaries

These integrations are implemented but were not tested end-to-end against a live PostgreSQL server, cloud credentials/object-storage service, or a Torch-native runtime in this release session. External services, mutable databases, subprocess side effects, notebook kernels, native extensions, hardware, and changing data remain explicit evidence boundaries rather than claims of universal deterministic replay. RunProof is not a sandbox, code generator, replacement for Git, or guarantee that an arbitrary Python program or scientific conclusion is correct.

## 0.1.2 — version consistency fix

This patch aligns `runproof_engine.__version__` with the distribution metadata and adds a regression test that compares the package version to `pyproject.toml`.

## 0.1.1 — path resolution fix

This patch resolves relative run roots before artifact creation. Outputs now remain safely inside an absolute artifact directory even when the caller uses `root="runs"`. A regression test covers the original failure mode.

## 0.1.0 — local evidence core

This release contains the first complete local core of RunProof: named run contexts, real file fingerprints, explicit input capture, bounded and redacted summaries, CSV and JSONL metadata, function source fingerprints, environment snapshots, step tracing, output artifacts, assertions, policy authorization, real HTTP request recording, integrity manifests, replay readiness checks, replay comparison hooks, Explainable Diff, CLI inspection, verification, and run comparison.

The core intentionally does not pretend to instrument arbitrary Python automatically or to reproduce arbitrary runtime state without a workflow runner. Cloud publishing, package installation, shell execution, and specialized adapters remain explicit extension points protected by policy.
