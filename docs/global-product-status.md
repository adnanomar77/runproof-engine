# RunProof Engine — Global Product Status

## Executive conclusion

نعم، يمكننا تحويل RunProof إلى منتج عالمي واسع يغطي تلقائيًا معظم أنماط Python الشائعة. لكن لا يمكن، تقنيًا أو علميًا، ضمان إعادة إنتاج كل برنامج Python عشوائي بنسبة 100%؛ فالنتيجة قد تعتمد على خدمة خارجية، ساعة النظام، العشوائية، نظام التشغيل، hardware، مكتبة native، أو حالة بيانات لا تملك RunProof وسيلة لالتقاطها. لذلك الوعد الصحيح هو: **التقاط آلي واسع مع إثبات صريح للحدود، وليس ادعاءً كاذبًا بأن كل تنفيذ قابل لإعادة الإنتاج**.

## What has been implemented

انتقل المشروع من نواة `0.1.x` التي تتطلب التصريح اليدوي إلى checkpoint تطويري في GitHub يستعد للإصدار `0.2.0`. التغييرات موجودة في المستودع العام [runproof-engine](https://github.com/adnanomar77/runproof-engine)، بينما لم تُنشر `0.2.0` على PyPI بعد؛ الإصدار المنشور الحالي ما زال `0.1.2`.

| Capability | Current status |
| --- | --- |
| Explicit `verified(...)` API | Implemented and backward-compatible |
| Automatic whole-script entry point | Implemented as `runproof run script.py` |
| Embeddable automatic context | Implemented as `auto_run(...)` |
| Python execution observation | `sys.monitoring` on Python 3.12+ and `sys.settrace` fallback on Python 3.10–3.11 |
| Runtime audit observation | Implemented for selected file, process, socket, and related events |
| Standard-library HTTP adapter | `urllib` adapter implemented with query redaction |
| Automatic output archiving | Implemented through `capture_outputs` and `--capture-output` |
| Real replay | Implemented as user-controlled re-execution and artifact comparison; no silent arbitrary re-execution |
| Integrity verification | Implemented with SHA-256 manifests and boundary-aware statuses |
| Explainable Diff | Compares inputs, steps, outputs, observations, environment, boundaries, and execution signatures |
| Causal explanation | Candidate explanations are emitted as `inference`, not presented as proven causality |
| Cross-platform CI | Configured for Python 3.10–3.14 on Ubuntu, macOS, and Windows |
| Secure PyPI release path | GitHub OIDC Trusted Publishing workflow added; it still requires PyPI-side configuration |

## Verification results

The local source tree passes the current test suite, `ruff`, `compileall`, package build, and `twine check`. The latest successful CI run before the release-preparation commit covered the configured Python and operating-system matrix. A genuine compatibility failure was discovered in CI on Python 3.10/Windows (`typing.Self` and `co_qualname`) and fixed before the successful rerun. This is important evidence that the project is being tested honestly rather than being declared compatible without running it.

The source currently contains **18 tests** covering real file inputs, artifacts, integrity tampering, policy decisions, HTTP against a local real server, automatic tracing, runtime audit events, automatic output capture, replay, boundaries, Explainable Diff, and CLI behavior. These tests are meaningful regression coverage, but they do not yet prove production readiness for every Python ecosystem or workload.

## What “automatic” means

The architecture follows a layered model. The baseline runtime observes Python calls, returns, exceptions, selected audit events, process lifecycle, environment metadata, and declared outputs. Boundary adapters add stronger evidence for libraries such as HTTP clients, database drivers, dataframe engines, object stores, notebooks, queues, and machine-learning frameworks. Unsupported or opaque boundaries are recorded explicitly.

Python itself provides execution monitoring through `sys.monitoring` beginning in Python 3.12, with selectable callbacks for execution events. Older supported versions require a `sys.settrace` fallback. The official documentation also states that tracing is thread-specific, which means that a serious implementation must handle thread propagation and must budget for overhead.[1] OpenTelemetry demonstrates a related industry pattern: Python zero-code instrumentation attaches an agent and primarily uses monkey patching for supported libraries, rather than magically covering every arbitrary library.[2]

> “Automatic instrumentation with Python uses a Python agent that can be attached to any Python application. This agent primarily uses monkey patching to modify library functions at runtime.” — OpenTelemetry documentation.[2]

RunProof must therefore report three coverage tiers. Common Python execution and supported adapters can be captured automatically. Specialized libraries can be supported through independently tested plugins. Native code, external systems, hardware-dependent behavior, missing data, and uncontrolled nondeterminism remain explicit boundaries. Python’s audit-hook documentation warns that audit hooks are not a sandbox and can be bypassed by hostile code, so RunProof must never sell tracing as isolation or security containment.[3]

## What is still required for a truly global production product

The current work is a strong foundation, not the final universal product. The next major engineering stage should implement tested adapters for `requests`/HTTPX, pandas, Polars, SQLite/PostgreSQL, subprocess propagation, common object stores, notebooks, queues, and common ML workflows. Each adapter must declare what it captures, what it redacts, how it replays, and what it cannot prove.

The replay layer must then evolve from “user-controlled runner plus comparison” to a contract-driven replay engine. Deterministic replay may substitute captured HTTP responses or input blobs only when the user opts in and the policy permits it. Live replay must use current services and report the resulting boundaries. No mode should silently perform destructive effects.

The evidence model should become a content-addressed provenance graph rather than a manifest containing only lists. It should connect reads, writes, calls, derived outputs, environment changes, subprocesses, and checks. The system should export OpenTelemetry traces for interoperability while retaining RunProof’s own artifact schema and cryptographic digests. PEP 751’s lock-file model provides a useful standard basis for recording package versions, markers, hashes, wheels, and installation sources, but a locked dependency set still cannot reproduce the operating system, hardware, external service state, or changing data.[4]

Performance and security need first-class gates. Automatic tracing must be benchmarked on representative workloads and support sampling or scope restrictions. Artifacts need size limits, configurable redaction, optional encryption, external integrity anchors, and clear handling of secrets. The project must add fuzzing for manifest loading and path handling, subprocess and thread tests, native-extension boundary tests, adapter compatibility matrices, and failure-injection scenarios.

## Release position

The current code has been prepared as `0.2.0` in the source tree and a secure release workflow has been added. It must not be called “the final global release” yet. The PyPI account currently has no usable publishing credential in the environment, so the correct next release path is to configure PyPI Trusted Publishing for `adnanomar77/runproof-engine`, create the `v0.2.0` tag only after the final CI run is green, and let GitHub publish the distributions through OIDC. The previously created broad PyPI token should be deleted or rotated from PyPI’s token-management page; it must not be embedded in source, workflow files, or chat messages.

The most accurate description today is: **RunProof Engine is a real, open-source, local-first evidence and replay foundation with automatic Python observation, boundary-aware verification, adapters, and cross-platform CI. It is ready for the next expansion cycle, but it is not yet an all-Python universal recorder or a guarantee of perfect reproducibility.**

## References

[1]: https://docs.python.org/3/library/sys.monitoring.html "Python 3.14 documentation — sys.monitoring"

[2]: https://opentelemetry.io/docs/zero-code/python/ "OpenTelemetry — Python zero-code instrumentation"

[3]: https://docs.python.org/3/library/sys.html#sys.addaudithook "Python 3.14 documentation — sys.addaudithook"

[4]: https://peps.python.org/pep-0751/ "PEP 751 — A file format to record Python dependencies for installation reproducibility"
