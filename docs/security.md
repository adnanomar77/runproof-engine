# RunProof security model

RunProof is an evidence and policy library, not an operating-system sandbox. A Python process remains able to do whatever its operating-system user is allowed to do. Applications that execute untrusted generated code must place that code in a separate worker or sandbox with filesystem, network, CPU, memory, and syscall restrictions.

## Default behavior

The core allows declared local reads, artifact writes inside the run directory, and declared Python calls. Network, upload, publish, shell, delete, and package installation are approval-gated. An application can deny any action through `Policy.denied_actions`.

## Secrets

Environment snapshots contain interpreter and package metadata, not arbitrary environment values. Trace payloads use bounded summaries and redact keys that look like passwords, tokens, API keys, credentials, or authorization headers. This is a defense-in-depth measure, not a proof that every possible secret has been detected. Users should review artifacts before sharing them.

## External services

The `request()` adapter authorizes before opening a URL, caps the response body captured in memory, fingerprints the response, and stores a redacted request description. It does not store authorization headers. Network sources can change; their replay status must therefore be treated as conditional unless the response is explicitly captured under the user's data policy.

## Path safety

Output paths are resolved under the run's `outputs` directory. Absolute paths and traversal outside that directory are rejected. Input copying is opt-in and is written under the run's `inputs` directory.

## Integrity

RunProof writes per-input and per-output fingerprints and an artifact-level `integrity.json`. The integrity file itself should be stored or hashed externally when tamper evidence matters. RunProof does not claim to provide cryptographic non-repudiation without an external trust anchor.

## Reporting failures

A blocked action is a normal recorded run outcome, not a silent success. A failed check produces `failed` or `verified_with_warnings` according to policy. A changed input or artifact is reported as `non_reproducible` rather than silently updating history.
