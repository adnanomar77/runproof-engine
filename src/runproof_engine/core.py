from __future__ import annotations

import json
import shutil
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from types import TracebackType
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .policy import Policy, PolicyDenied, safe_default_policy
from .provenance import ProvenanceGraph
from .utils import (
    environment_snapshot,
    file_metadata,
    fingerprint,
    function_descriptor,
    safe_value,
    sha256_bytes,
    sha256_file,
    summarize,
    utc_now,
    write_json,
)


class RunProofError(RuntimeError):
    """Base exception for RunProof failures."""


class ReplayUnavailable(RunProofError):
    """Raised when an artifact does not contain enough information for replay."""


@dataclass
class CheckRecord:
    name: str
    passed: bool
    message: str
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "created_at": self.created_at,
        }


@dataclass
class StepRecord:
    name: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    function: dict[str, Any]
    input_summaries: list[dict[str, Any]]
    output_summary: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    replayable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": round(self.duration_ms, 3),
            "function": self.function,
            "inputs": self.input_summaries,
            "output": self.output_summary,
            "error": self.error,
            "replayable": self.replayable,
        }


@dataclass
class RunResult:
    run_id: str
    name: str
    status: str
    artifact_dir: Path
    started_at: str
    finished_at: str | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "status": self.status,
            "artifact_dir": str(self.artifact_dir),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }

    def summary(self) -> str:
        return (
            f"status={self.status} name={self.name} run_id={self.run_id} "
            f"artifact_dir={self.artifact_dir}"
        )


class RunContext:
    """Record a declared Python workflow as a real, inspectable run artifact."""

    def __init__(
        self,
        name: str,
        *,
        root: str | Path = "runs",
        copy_inputs: bool = False,
        capture_environment: bool = True,
        fail_on_check: bool = False,
        policy: Policy | None = None,
    ) -> None:
        self.name = name
        self.root = Path(root).expanduser().resolve()
        self.copy_inputs = copy_inputs
        self.capture_environment = capture_environment
        self.fail_on_check = fail_on_check
        self.policy = policy or safe_default_policy()
        self.run_id = f"{utc_now().replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:10]}"
        self._provenance = ProvenanceGraph(run_id=self.run_id)
        self.artifact_dir = self.root / self._safe_name(name) / self.run_id
        self._started_at = utc_now()
        self._started_clock = 0.0
        self._finished_at: str | None = None
        self._steps: list[StepRecord] = []
        self._checks: list[CheckRecord] = []
        self._inputs: list[dict[str, Any]] = []
        self._outputs: list[dict[str, Any]] = []
        self._observations: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._boundaries: list[dict[str, Any]] = []
        self._environment: dict[str, Any] | None = None
        self._status = "running"
        self._error: dict[str, Any] | None = None
        self.result: RunResult = RunResult(
            run_id=self.run_id,
            name=self.name,
            status=self._status,
            artifact_dir=self.artifact_dir,
            started_at=self._started_at,
        )

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
        return safe.strip("_") or "run"

    def __enter__(self) -> RunContext:  # noqa: PYI034 - runtime annotation is compatible with Python 3.10
        self.artifact_dir.mkdir(parents=True, exist_ok=False)
        for directory in ("inputs", "outputs", "checks", "execution", "environment"):
            (self.artifact_dir / directory).mkdir()
        self._started_clock = perf_counter()
        self._event("run_started", {"name": self.name})
        if self.capture_environment:
            self._environment = environment_snapshot()
            write_json(self.artifact_dir / "environment" / "snapshot.json", self._environment)
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> bool:
        if isinstance(exc, PolicyDenied):
            self._status = "blocked"
            self._error = {
                "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
                "message": str(exc),
            }
            self._event("action_blocked", self._error)
        elif exc is not None:
            self._status = "failed"
            self._error = {
                "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
                "message": str(exc),
                "traceback": "".join(traceback.format_exception(type(exc), exc, tb)),
            }
            self._event("run_failed", self._error)
        elif any(not check.passed for check in self._checks):
            self._status = "failed" if self.fail_on_check else "verified_with_warnings"
            self._event("checks_completed", {"failed": True})
        elif self._boundaries:
            self._status = "verified_with_boundaries"
            self._event("checks_completed", {"failed": False, "boundaries": len(self._boundaries)})
        else:
            self._status = "verified"
            self._event("checks_completed", {"failed": False})
        self._finalize()
        return False

    def _event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._events.append({
            "event": event_type,
            "at": utc_now(),
            "payload": safe_value(payload),
        })

    def boundary(
        self,
        kind: str,
        *,
        target: str | None = None,
        reason: str,
        replay: str = "unknown",
    ) -> None:
        """Record an observed effect whose complete state is outside the artifact."""
        record = {
            "kind": kind,
            "target": target,
            "reason": reason,
            "replay": replay,
        }
        self._boundaries.append(record)
        node = self._provenance.add_node("boundary", str(target or kind), digest=fingerprint(record), attributes=record)
        self._provenance.link_to_run(node, "limits")
        self._event("evidence_boundary", record)

    def authorize(self, action: str, *, approved: bool = False, target: str | None = None) -> dict[str, Any]:
        """Authorize a sensitive action and record the decision in the trace."""
        try:
            decision = self.policy.authorize(action, approved=approved, target=target)
        except PolicyDenied as error:
            self._event("action_blocked", {"action": action, "target": target, "reason": str(error)})
            raise
        self._event("action_authorized", decision)
        return decision

    def input(self, path: str | Path, *, name: str | None = None, copy: bool | None = None) -> Path:
        """Register a real file input and return its resolved path."""
        should_copy = self.copy_inputs if copy is None else copy
        record_name = name or Path(path).stem or "input"
        metadata = file_metadata(path)
        destination: str | None = None
        if should_copy:
            target = self.artifact_dir / "inputs" / Path(path).name
            if target.exists():
                target = self.artifact_dir / "inputs" / f"{fingerprint(str(path))[:8]}-{Path(path).name}"
            shutil.copy2(path, target)
            destination = str(target.relative_to(self.artifact_dir))
            metadata["captured_copy"] = destination
        metadata["name"] = record_name
        self._inputs.append(metadata)
        node = self._provenance.add_node("input", record_name, digest=metadata.get("sha256"), attributes=metadata)
        self._provenance.link_to_run(node, "input")
        self._event("input_registered", metadata)
        write_json(self.artifact_dir / "inputs" / f"{self._safe_name(record_name)}.json", metadata)
        return Path(metadata["path"])

    def step(self, name: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a callable and record a bounded, privacy-safe step trace."""
        started_at = utc_now()
        clock = perf_counter()
        descriptor = function_descriptor(function)
        self._event("step_started", {"name": name, "function": descriptor})
        try:
            output = function(*args, **kwargs)
            finished_at = utc_now()
            record = StepRecord(
                name=name,
                status="completed",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=(perf_counter() - clock) * 1000,
                function=descriptor,
                input_summaries=[summarize(value) for value in args],
                output_summary=summarize(output),
                replayable=self._is_json_replayable(args, kwargs, output),
            )
            self._steps.append(record)
            step_node = self._provenance.add_node("step", name, digest=descriptor.get("source_sha256"), attributes=record.to_dict())
            self._provenance.add_edge(self._provenance.run_node, step_node, "contains")
            for index, summary in enumerate(record.input_summaries):
                input_node = self._provenance.add_node("value", f"{name}:input:{index}", digest=summary.get("fingerprint"), attributes=summary)
                self._provenance.add_edge(input_node, step_node, "used")
            if record.output_summary and record.output_summary.get("fingerprint"):
                output_node = self._provenance.add_node("value", f"{name}:output", digest=record.output_summary["fingerprint"], attributes=record.output_summary)
                self._provenance.add_edge(step_node, output_node, "produces")
            self._event("step_completed", {"name": name, "output": record.output_summary})
            return output
        except Exception as error:
            finished_at = utc_now()
            record = StepRecord(
                name=name,
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=(perf_counter() - clock) * 1000,
                function=descriptor,
                input_summaries=[summarize(value) for value in args],
                error={
                    "type": f"{type(error).__module__}.{type(error).__qualname__}",
                    "message": str(error),
                },
            )
            self._steps.append(record)
            step_node = self._provenance.add_node("step", name, digest=descriptor.get("source_sha256"), attributes=record.to_dict())
            self._provenance.add_edge(self._provenance.run_node, step_node, "contains")
            self._event("step_failed", {"name": name, "error": record.error or {}})
            raise

    def output(self, path: str | Path, value: Any, *, name: str | None = None) -> Path:
        """Write a JSON-safe output inside the artifact and record its fingerprint."""
        target = self._output_target(path)
        if target.suffix.lower() not in {".json", ".jsonl"}:
            raise RunProofError("RunContext.output currently supports .json or .jsonl; use save_file for binary/text artifacts")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        record = {
            "name": name or target.stem,
            "path": str(target.relative_to(self.artifact_dir)),
            "size_bytes": target.stat().st_size,
            "sha256": file_metadata(target)["sha256"],
            "value_summary": summarize(value),
        }
        self._outputs.append(record)
        node = self._provenance.add_node("output", str(record["name"]), digest=record.get("sha256"), attributes=record)
        self._provenance.link_to_run(node, "output")
        self._event("output_saved", record)
        return target

    def capture_file(self, source: str | Path, *, name: str | None = None) -> Path:
        """Copy a real file written by the observed process into the artifact outputs."""
        source_path = Path(source).expanduser().resolve()
        metadata = file_metadata(source_path)
        target_name = name or source_path.name
        target = self._output_target(Path("auto") / target_name)
        if target.exists():
            target = self._output_target(Path("auto") / f"{fingerprint(str(source_path))[:8]}-{target_name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        metadata.update({
            "name": target_name,
            "source_path": str(source_path),
            "path": str(target.relative_to(self.artifact_dir)),
            "captured_copy": str(target.relative_to(self.artifact_dir)),
        })
        self._outputs.append(metadata)
        node = self._provenance.add_node("output", str(metadata["name"]), digest=metadata.get("sha256"), attributes=metadata)
        self._provenance.link_to_run(node, "output")
        self._event("automatic_output_captured", metadata)
        return target

    def save_file(self, path: str | Path, *, source: str | Path | None = None, content: str | bytes | None = None) -> Path:
        """Save a real text or binary artifact and register its hash."""
        target = self._output_target(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source is not None and content is not None:
            raise ValueError("provide source or content, not both")
        if source is not None:
            shutil.copy2(source, target)
        elif isinstance(content, bytes):
            target.write_bytes(content)
        elif isinstance(content, str):
            target.write_text(content, encoding="utf-8")
        else:
            raise ValueError("source or content is required")
        record = {
            "name": target.stem,
            "path": str(target.relative_to(self.artifact_dir)),
            "size_bytes": target.stat().st_size,
            "sha256": file_metadata(target)["sha256"],
        }
        self._outputs.append(record)
        node = self._provenance.add_node("output", str(record["name"]), digest=record.get("sha256"), attributes=record)
        self._provenance.link_to_run(node, "output")
        self._event("file_saved", record)
        return target

    def observe(self, value: Any, *, name: str) -> Any:
        """Record a bounded summary of an in-memory value without copying its full contents."""
        record = {"name": name, "summary": summarize(value)}
        self._observations.append(record)
        summary = record.get("summary") or {}
        node = self._provenance.add_node("observation", name, digest=summary.get("fingerprint"), attributes=record)
        self._provenance.link_to_run(node, "observes")
        self._event("value_observed", record)
        return value

    def external_call(
        self,
        name: str,
        *,
        provider: str,
        request: Any,
        response: Any,
        status_code: int | None = None,
        approved: bool = False,
        _authorized: bool = False,
    ) -> Any:
        """Record a completed real external call after policy authorization.

        The core package never performs the network request and never stores
        credentials. The caller performs the request, then gives RunProof a
        privacy-safe request and the response to fingerprint and summarize.
        """
        if not _authorized:
            self.authorize("network", approved=approved, target=provider)
        response_summary = summarize(response)
        response_summary.pop("value", None)
        record = {
            "name": name,
            "provider": provider,
            "request": safe_value(request),
            "response": response_summary,
            "response_fingerprint": fingerprint(response),
            "status_code": status_code,
        }
        self._event("external_call", record)
        return response

    def request(
        self,
        name: str,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | str | dict[str, Any] | None = None,
        timeout: float = 30.0,
        approved: bool = False,
    ) -> Any:
        """Perform and record a real HTTP request after explicit authorization."""
        self.authorize("network", approved=approved, target=url)
        request_headers = dict(headers or {})
        safe_headers = {
            key: "[REDACTED]" if key.lower() in {"authorization", "proxy-authorization", "cookie", "set-cookie"} else value
            for key, value in request_headers.items()
        }
        if isinstance(body, dict):
            request_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            request_body = body.encode("utf-8")
        else:
            request_body = body
        request = Request(url, data=request_body, headers=request_headers, method=method.upper())
        request_meta = {
            "method": method.upper(),
            "url": url,
            "headers": safe_headers,
            "body_sha256": sha256_bytes(request_body) if request_body else None,
        }
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(10 * 1024 * 1024 + 1)
                truncated = len(raw) > 10 * 1024 * 1024
                raw = raw[:10 * 1024 * 1024]
                content_type = response.headers.get("Content-Type", "")
                text = raw.decode("utf-8", errors="replace")
                parsed: Any = text
                if "json" in content_type.lower():
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = text
                self.external_call(
                    name,
                    provider=url,
                    request=request_meta,
                    response=parsed,
                    status_code=getattr(response, "status", None),
                    approved=True,
                    _authorized=True,
                )
                self._event("external_response", {"name": name, "content_type": content_type, "truncated": truncated, "bytes": len(raw)})
                return parsed
        except (HTTPError, URLError, TimeoutError) as error:
            self._event("external_call_failed", {
                "name": name,
                "provider": url,
                "error_type": type(error).__name__,
                "message": str(error),
            })
            raise

    def check_schema(self, value: Any, *, required_columns: list[str], types: dict[str, str] | None = None) -> bool:
        columns = getattr(value, "columns", None)
        actual = [str(column) for column in list(columns)] if columns is not None else []
        missing = [column for column in required_columns if column not in actual]
        passed = not missing
        message = "schema contains required columns" if passed else f"missing columns: {missing}"
        if passed and types:
            dtypes = getattr(value, "dtypes", {})
            mismatches = []
            for column, expected in types.items():
                if column in dtypes and not self._type_matches(dtypes[column], expected):
                    mismatches.append(f"{column}: expected {expected}, got {dtypes[column]}")
            if mismatches:
                passed = False
                message = "; ".join(mismatches)
        return self._record_check("schema", passed, message)

    @staticmethod
    def _type_matches(actual: Any, expected: str) -> bool:
        actual_text = str(actual).lower()
        expected_text = expected.lower()
        aliases = {
            "number": ("int", "float", "decimal", "double", "number"),
            "integer": ("int", "integer"),
            "float": ("float", "double"),
            "string": ("object", "string", "str", "unicode"),
            "datetime": ("datetime", "date", "time"),
            "boolean": ("bool", "boolean"),
        }
        tokens = aliases.get(expected_text, (expected_text,))
        return any(token in actual_text for token in tokens)

    def assert_true(self, condition: bool, message: str = "assertion passed", *, name: str | None = None) -> bool:
        return self._record_check(name or "assert_true", bool(condition), message if condition else f"FAILED: {message}")

    def assert_columns(self, value: Any, columns: list[str]) -> bool:
        actual = [str(column) for column in list(getattr(value, "columns", []))]
        missing = [column for column in columns if column not in actual]
        return self._record_check("columns", not missing, "columns present" if not missing else f"missing columns: {missing}")

    def assert_non_negative(self, value: Any, *, name: str = "non_negative") -> bool:
        try:
            passed = bool((value >= 0).all()) if hasattr(value, "all") else all(item >= 0 for item in value)
        except (AttributeError, TypeError, ValueError) as error:
            return self._record_check(name, False, f"unable to evaluate: {error}")
        return self._record_check(name, passed, "all values are non-negative" if passed else "negative value found")

    def assert_file(self, path: str | Path) -> bool:
        target = self._artifact_target(path)
        passed = target.is_file()
        return self._record_check("file_exists", passed, f"file exists: {target.name}" if passed else f"missing file: {target}")

    def _record_check(self, name: str, passed: bool, message: str) -> bool:
        check = CheckRecord(name=name, passed=passed, message=message)
        self._checks.append(check)
        check_record = check.to_dict()
        node = self._provenance.add_node("check", name, digest=fingerprint(check_record), attributes=check_record)
        self._provenance.add_edge(self._provenance.run_node, node, "asserts")
        self._event("check", check_record)
        return passed

    def _output_target(self, path: str | Path) -> Path:
        relative = Path(path)
        if relative.is_absolute():
            raise RunProofError("output paths must be relative")
        if relative.parts and relative.parts[0] == "outputs":
            relative = Path(*relative.parts[1:])
        output_root = (self.artifact_dir / "outputs").resolve()
        candidate = (output_root / relative).resolve()
        if candidate != output_root and output_root not in candidate.parents:
            raise RunProofError("output path escapes the outputs directory")
        return candidate

    def _artifact_target(self, path: str | Path) -> Path:
        target = Path(path)
        if target.is_absolute():
            raise RunProofError("artifact paths must be relative to the run artifact directory")
        candidate = (self.artifact_dir / target).resolve()
        if self.artifact_dir.resolve() not in candidate.parents and candidate != self.artifact_dir.resolve():
            raise RunProofError("artifact path escapes the run directory")
        return candidate

    @staticmethod
    def _is_json_replayable(args: tuple[Any, ...], kwargs: dict[str, Any], output: Any) -> bool:
        try:
            json.dumps({"args": args, "kwargs": kwargs, "output": output}, default=lambda value: safe_value(value, max_items=20, max_text=100))
            return all(isinstance(value, (str, int, float, bool, type(None), list, tuple, dict)) for value in args)
        except (TypeError, ValueError, OverflowError):
            return False

    def _finalize(self) -> None:
        self._finished_at = utc_now()
        self._event("run_finished", {"status": self._status})
        self.result = RunResult(
            run_id=self.run_id,
            name=self.name,
            status=self._status,
            artifact_dir=self.artifact_dir,
            started_at=self._started_at,
            finished_at=self._finished_at,
            error=self._error,
        )
        manifest = {
            "schema_version": "0.1",
            "run": self.result.to_dict(),
            "inputs": self._inputs,
            "outputs": self._outputs,
            "observations": self._observations,
            "boundaries": self._boundaries,
            "steps": [step.to_dict() for step in self._steps],
            "checks": [check.to_dict() for check in self._checks],
            "environment": self._environment,
            "policy": {
                "allowed_actions": sorted(self.policy.allowed_actions),
                "approval_required": sorted(self.policy.approval_required),
                "denied_actions": sorted(self.policy.denied_actions),
            },
            "replay": {
                "possible_steps": sum(step.replayable for step in self._steps),
                "boundaries": len(self._boundaries),
                "total_steps": len(self._steps),
                "note": "Replayability is reported from captured evidence; external sources may remain non-deterministic.",
            },
        }
        write_json(self.artifact_dir / "manifest.json", manifest)
        write_json(self.artifact_dir / "provenance.json", self._provenance.to_dict())
        write_json(self.artifact_dir / "execution" / "trace.json", self._events)
        write_json(self.artifact_dir / "checks" / "results.json", [check.to_dict() for check in self._checks])
        write_json(self.artifact_dir / "execution" / "steps.json", [step.to_dict() for step in self._steps])
        write_json(self.artifact_dir / "execution" / "outputs.json", self._outputs)
        integrity_records = []
        for artifact in sorted(self.artifact_dir.rglob("*")):
            if artifact.is_file() and artifact.name != "integrity.json":
                integrity_records.append({
                    "path": str(artifact.relative_to(self.artifact_dir)),
                    "sha256": sha256_file(artifact),
                    "size_bytes": artifact.stat().st_size,
                })
        write_json(self.artifact_dir / "integrity.json", {
            "schema_version": "0.1",
            "files": integrity_records,
            "note": "Keep an external copy of this file or its digest for tamper evidence against the artifact itself.",
        })


def verified(name: str, **kwargs: Any) -> RunContext:
    return RunContext(name, **kwargs)
