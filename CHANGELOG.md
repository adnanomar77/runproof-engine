# Changelog

## 0.1.0 — local evidence core

This release contains the first complete local core of RunProof: named run contexts, real file fingerprints, explicit input capture, bounded and redacted summaries, CSV and JSONL metadata, function source fingerprints, environment snapshots, step tracing, output artifacts, assertions, policy authorization, real HTTP request recording, integrity manifests, replay readiness checks, replay comparison hooks, Explainable Diff, CLI inspection, verification, and run comparison.

The core intentionally does not pretend to instrument arbitrary Python automatically or to reproduce arbitrary runtime state without a workflow runner. Cloud publishing, package installation, shell execution, and specialized adapters remain explicit extension points protected by policy.
