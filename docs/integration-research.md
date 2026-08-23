# Integration Research Notes

## HTTP instrumentation

OpenTelemetry's requests instrumentation documentation shows that requests can expose request and response hooks. The request hook receives a `requests.PreparedRequest`; the response hook receives the request object and `requests.Response`. This supports a RunProof adapter that records method, redacted URL, headers, body digest, status, timing, and bounded response metadata without requiring a full monkey-patch of the library.[1]

HTTPX's official documentation exposes `request` and `response` event hooks on both clients and async clients. Request hooks run after preparation and before network transmission; response hooks run after fetching and before returning to the caller. Response hooks run before the body is read, so consuming the body for capture would change streaming behavior. AsyncClient hooks must be async functions.[2]

## Adapter contract implications

Adapters should prefer the library's documented hook system when available, and use monkey-patching only as a compatibility fallback. Each adapter must declare whether it observes metadata only, captures a bounded body, or consumes a stream; whether it supports sync, async, and streaming APIs; and whether it can replay from captured evidence. A metadata-only network adapter must create a boundary rather than claiming full reproducibility.

The same contract applies to pandas, Polars, SQLAlchemy, SQLite, PostgreSQL, subprocess, Jupyter, object storage, and ML integrations: capture stable identities and hashes at high-value boundaries, avoid altering semantics, expose opt-in content capture, and record unsupported cases explicitly.

## References

[1]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html "OpenTelemetry requests instrumentation"

[2]: https://www.python-httpx.org/advanced/event-hooks/ "HTTPX event hooks"
