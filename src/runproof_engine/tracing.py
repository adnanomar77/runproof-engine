"""Small dependency-free distributed tracing core for RunProof."""

from __future__ import annotations

import contextvars
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import time_ns
from typing import Any

from .utils import safe_value

_current_span: contextvars.ContextVar[str | None] = contextvars.ContextVar("runproof_current_span", default=None)


def _new_trace_id() -> str:
    return secrets.token_hex(16)


def _new_span_id() -> str:
    return secrets.token_hex(8)


def parse_traceparent(value: str | None) -> tuple[str, str, int] | None:
    """Parse a W3C traceparent header, returning trace id, parent span id, flags."""
    if not value:
        return None
    parts = value.strip().split("-")
    if len(parts) != 4 or parts[0] != "00":
        return None
    _version, trace_id, span_id, flags = parts
    if len(trace_id) != 32 or len(span_id) != 16 or len(flags) != 2:
        return None
    if not all(character in "0123456789abcdefABCDEF" for character in trace_id + span_id + flags):
        return None
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    return trace_id.lower(), span_id.lower(), int(flags, 16)


def format_traceparent(trace_id: str, span_id: str, flags: int = 1) -> str:
    return f"00-{trace_id}-{span_id}-{flags:02x}"


@dataclass
class Span:
    tracer: Tracer
    name: str
    span_id: str
    parent_span_id: str | None
    start_time_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "UNSET"
    end_time_ns: int | None = None
    error: dict[str, str] | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[str(key)] = value

    def set_status(self, status: str) -> None:
        self.status = status

    def end(self, *, status: str | None = None) -> None:
        if self.end_time_ns is None:
            self.end_time_ns = time_ns()
            if status is not None:
                self.status = status
            self.tracer._finished.append(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.tracer.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time_unix_nano": self.start_time_ns,
            "end_time_unix_nano": self.end_time_ns or self.start_time_ns,
            "status": self.status,
            "attributes": safe_value(self.attributes),
            "error": self.error,
        }


class Tracer:
    """In-process tracer that exports deterministic shape and W3C propagation metadata."""

    def __init__(self, *, trace_id: str | None = None, parent_span_id: str | None = None, flags: int = 1) -> None:
        self.trace_id = trace_id or _new_trace_id()
        self.parent_span_id = parent_span_id
        self.flags = flags
        self._finished: list[Span] = []

    @classmethod
    def from_environment(cls) -> Tracer:
        parsed = parse_traceparent(__import__("os").environ.get("TRACEPARENT"))
        if parsed is None:
            return cls()
        trace_id, parent_span_id, flags = parsed
        return cls(trace_id=trace_id, parent_span_id=parent_span_id, flags=flags)

    @contextmanager
    def span(self, name: str, *, attributes: dict[str, Any] | None = None) -> Iterator[Span]:
        parent = _current_span.get() or self.parent_span_id
        span = Span(
            tracer=self,
            name=name,
            span_id=_new_span_id(),
            parent_span_id=parent,
            start_time_ns=time_ns(),
            attributes=dict(attributes or {}),
        )
        token = _current_span.set(span.span_id)
        try:
            yield span
        except BaseException as error:
            span.status = "ERROR"
            span.error = {"type": f"{type(error).__module__}.{type(error).__qualname__}", "message": str(error)[:500]}
            raise
        finally:
            span.end()
            _current_span.reset(token)

    def current_span_id(self) -> str | None:
        return _current_span.get()

    def traceparent(self) -> str:
        return format_traceparent(self.trace_id, self._finished[-1].span_id if self._finished else self.parent_span_id or _new_span_id(), self.flags)

    def export(self) -> list[dict[str, Any]]:
        return [span.to_dict() for span in self._finished]


__all__ = ["Span", "Tracer", "format_traceparent", "parse_traceparent"]
