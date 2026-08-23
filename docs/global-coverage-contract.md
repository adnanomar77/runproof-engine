# RunProof Global Coverage Contract

## Product promise

RunProof aims to capture and explain most common Python workflows automatically, without requiring every function to be wrapped manually. It will produce execution evidence, provenance, integrity checks, and replay guidance for the parts it can observe and will clearly mark unknown or non-deterministic boundaries.

## Automatic coverage tiers

### Tier A — automatic and deterministic where supported

The runtime captures Python entry and exit points, exceptions, file reads and writes, environment metadata, installed distributions, selected database drivers, HTTP clients, subprocess metadata, random seeds where available, and declared or detected artifacts. It records hashes and bounded summaries while redacting secrets.

### Tier B — automatic with explicit integration adapters

Dataframes, notebooks, common ML frameworks, cloud object stores, queues, database transactions, distributed jobs, and agent/tool calls use adapters. The base runtime remains usable without every adapter, but each adapter declares exactly what it can and cannot prove.

### Tier C — explicit limitations

Opaque native extensions, external systems that provide no request identity or snapshot, hardware-dependent behavior, wall-clock and randomness without capture, deleted or inaccessible inputs, and side effects outside the process cannot be proven or replayed completely. RunProof records these boundaries rather than inventing evidence.

## Non-goals

RunProof will not claim that arbitrary Python can be reproduced exactly, will not capture secrets by default, will not silently execute dangerous actions, and will not present a verified status when required evidence is missing.

## Verification states

- `verified`: observed evidence is intact and all declared checks passed.
- `verified_with_boundaries`: evidence is intact but one or more external or non-deterministic boundaries remain.
- `non_reproducible`: evidence or required inputs differ, are missing, or fail integrity checks.
- `blocked`: policy prevented a sensitive action.
- `failed`: execution raised an error or a required check failed.

## Product differentiation

The central feature is not tracing alone. RunProof provides a provenance graph and Explainable Diff that connect input changes, environment changes, step changes, and output changes, and it refuses to label an incomplete run as fully verified.
