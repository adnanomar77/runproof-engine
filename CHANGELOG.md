# Changelog

## 0.1.2 — version consistency fix

This patch aligns `runproof_engine.__version__` with the distribution metadata and adds a regression test that compares the package version to `pyproject.toml`.

## 0.1.1 — path resolution fix

This patch resolves relative run roots before artifact creation. Outputs now remain safely inside an absolute artifact directory even when the caller uses `root="runs"`. A regression test covers the original failure mode.

## 0.1.0 — local evidence core

This release contains the first complete local core of RunProof: named run contexts, real file fingerprints, explicit input capture, bounded and redacted summaries, CSV and JSONL metadata, function source fingerprints, environment snapshots, step tracing, output artifacts, assertions, policy authorization, real HTTP request recording, integrity manifests, replay readiness checks, replay comparison hooks, Explainable Diff, CLI inspection, verification, and run comparison.

The core intentionally does not pretend to instrument arbitrary Python automatically or to reproduce arbitrary runtime state without a workflow runner. Cloud publishing, package installation, shell execution, and specialized adapters remain explicit extension points protected by policy.
