# RunProof usage

## A real file run

```python
from runproof_engine import verified


def read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def count_non_empty(lines):
    return sum(bool(line.strip()) for line in lines)

with verified("document_quality", root="runs", copy_inputs=True) as run:
    path = run.input("notes.txt", name="notes")
    lines = run.step("read_lines", read_lines, path)
    count = run.step("count_non_empty", count_non_empty, lines)
    run.assert_true(count >= 0, "count cannot be negative")
    run.output("summary.json", {"non_empty_lines": count})

print(run.result.summary())
```

The input is a real file. RunProof records its absolute path, size, SHA-256 fingerprint, and optional captured copy. It records the two declared steps and the assertion. The output is written inside the run artifact, not to an arbitrary path.

## Inspect an artifact

```bash
runproof inspect runs/document_quality/<run-id>
runproof inspect runs/document_quality/<run-id> --json
runproof verify runs/document_quality/<run-id>
```

`verify` checks that captured input paths and recorded outputs still match their stored fingerprints. A changed input produces `non_reproducible`; it does not silently update the previous run.

## Compare two runs

```python
from runproof_engine import load_run

first = load_run("runs/document_quality/<first-run-id>")
second = load_run("runs/document_quality/<second-run-id>")
comparison = first.diff(second)
print(comparison.render())
```

The comparison reports changed input fingerprints, step output fingerprints, code source fingerprints, output artifacts, checks, and environment fields. The explanations are evidence-based and do not claim causality beyond the captured facts.

## Sensitive actions

```python
from runproof_engine import Policy, PolicyDenied, verified

policy = Policy(
    allowed_actions={"read", "write_artifact", "execute_python"},
    approval_required={"upload"},
)

with verified("publish_report", root="runs", policy=policy) as run:
    run.authorize("upload", target="https://example.invalid", approved=False)
```

The action is blocked and the run is finalized with status `blocked`. Approval must be explicit:

```python
with verified("publish_report", root="runs", policy=policy) as run:
    run.authorize("upload", target="https://example.invalid", approved=True)
```

RunProof does not perform the upload itself in the core package. An adapter should call the external service only after authorization and should record privacy-safe request metadata.

## Replay semantics

```python
loaded = load_run("runs/document_quality/<run-id>")
report = loaded.replay(mode="strict")
print(report)
```

Without a user-supplied runner, replay validates integrity and returns `replay_ready`; it does not pretend it can reconstruct arbitrary Python state. A real workflow can supply a runner that creates a new artifact, after which RunProof compares the new run with the old one.

## Privacy

RunProof stores bounded summaries in traces. It redacts likely secret keys and never stores authorization headers through the core API. Copying full inputs is explicit with `copy_inputs=True` or `copy=True`. Users should review artifact contents before sharing them.
