# Changelog

## 0.2.0 — automatic observation and boundary-aware replay

### Added

- Added `auto_run` and `AutoCapture` for automatic Python call/return/exception observation.
- Added `sys.monitoring` support on Python 3.12+ with `sys.settrace` fallback for Python 3.10 and 3.11.
- Added bounded runtime audit observation for selected file, process, and socket events.
- Added adapter contracts and a standard-library `urllib` adapter with URL query redaction.
- Added automatic output capture through `capture_outputs` and CLI `--capture-output`.
- Added CLI `run` for observing a complete Python script and CLI `replay` for user-controlled re-execution and comparison.
- Added `verified_with_boundaries` status and explicit evidence-boundary records.
- Extended Explainable Diff to compare observations, boundaries, execution signatures, and causal candidates marked as inference.
- Added GitHub Actions compatibility matrix for Python 3.10–3.14 on Ubuntu, macOS, and Windows, plus package build validation.

### Verification

- 18 local tests pass with ruff and compileall.
- GitHub Actions passed across the configured operating-system and Python-version matrix for commit `a4f4e4e` before this version bump; the final release commit must pass CI again before publication.


## 0.1.2 — version consistency fix

This patch aligns `runproof_engine.__version__` with the distribution metadata and adds a regression test that compares the package version to `pyproject.toml`.

## 0.1.1 — path resolution fix

This patch resolves relative run roots before artifact creation. Outputs now remain safely inside an absolute artifact directory even when the caller uses `root="runs"`. A regression test covers the original failure mode.

## 0.1.0 — local evidence core

This release contains the first complete local core of RunProof: named run contexts, real file fingerprints, explicit input capture, bounded and redacted summaries, CSV and JSONL metadata, function source fingerprints, environment snapshots, step tracing, output artifacts, assertions, policy authorization, real HTTP request recording, integrity manifests, replay readiness checks, replay comparison hooks, Explainable Diff, CLI inspection, verification, and run comparison.

The core intentionally does not pretend to instrument arbitrary Python automatically or to reproduce arbitrary runtime state without a workflow runner. Cloud publishing, package installation, shell execution, and specialized adapters remain explicit extension points protected by policy.
