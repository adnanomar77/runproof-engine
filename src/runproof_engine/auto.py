"""Automatic runtime observation for RunProof contexts.

The observer records bounded Python execution events. It is intentionally not a
sandbox and does not serialize local variables or arbitrary object state.
"""

from __future__ import annotations

import os
import sys
import threading
import weakref
from pathlib import Path
from types import FrameType, TracebackType
from typing import Any

from .adapters import Adapter, default_adapters
from .core import RunContext
from .utils import safe_value, summarize


class AutoCapture:
    """Capture observable Python execution events for a :class:`RunContext`.

    ``sys.monitoring`` is used when available and when a free monitoring tool ID
    exists. Older Python versions use ``sys.settrace``. The observer excludes
    RunProof internals by default and can be narrowed with ``include_paths``.
    """

    _audit_lock = threading.Lock()
    _audit_installed = False
    _active_observers: weakref.WeakSet[AutoCapture] = weakref.WeakSet()
    _audit_events = frozenset({
        "open",
        "os.open",
        "os.remove",
        "os.rename",
        "os.chdir",
        "subprocess.Popen",
        "socket.connect",
    })

    def __init__(
        self,
        context: RunContext,
        *,
        include_paths: list[str | os.PathLike[str]] | None = None,
        include_stdlib: bool = False,
        backend: str = "auto",
        capture_returns: bool = True,
        capture_audit: bool = True,
        adapters: tuple[Adapter, ...] | list[Adapter] | None = None,
        capture_outputs: list[str | os.PathLike[str]] | None = None,
    ) -> None:
        if backend not in {"auto", "monitoring", "trace"}:
            raise ValueError("backend must be 'auto', 'monitoring', or 'trace'")
        self.context = context
        self.backend = backend
        self.include_stdlib = include_stdlib
        self.capture_returns = capture_returns
        self.capture_audit = capture_audit
        self.adapters = tuple(default_adapters() if adapters is None else adapters)
        self.capture_outputs = tuple(Path(path).expanduser() for path in (capture_outputs or []))
        self._uninstallers: list[Any] = []
        self.include_paths = [Path(path).expanduser().resolve() for path in (include_paths or [])]
        self._started = False
        self._stopped = False
        self._monitoring_id: int | None = None
        self._previous_trace: Any = None
        self._previous_thread_trace: Any = None
        self._package_root = Path(__file__).resolve().parent
        self._stdlib_roots = self._find_stdlib_roots()

    @staticmethod
    def _find_stdlib_roots() -> tuple[Path, ...]:
        roots: list[Path] = []
        try:
            roots.append(Path(os.__file__).resolve().parent)
        except (AttributeError, OSError):
            pass
        try:
            roots.append(Path(Path(sys.executable).resolve().parent, "../lib").resolve())
        except OSError:
            pass
        return tuple(roots)

    def __enter__(self) -> RunContext:
        self.context.__enter__()
        try:
            self.start()
        except Exception:
            self.context.__exit__(*sys.exc_info())
            raise
        return self.context

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self.stop()
        return self.context.__exit__(exc_type, exc, tb)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stopped = False
        if self.capture_audit:
            self._register_audit_observer()
        self._install_adapters()
        if self.backend in {"auto", "monitoring"} and self._start_monitoring():
            return
        if self.backend == "monitoring":
            raise RuntimeError("sys.monitoring is unavailable or no monitoring tool ID is free")
        self._start_trace()

    def stop(self) -> None:
        if not self._started or self._stopped:
            return
        self._capture_outputs()
        for uninstall in reversed(self._uninstallers):
            try:
                uninstall()
            except (RuntimeError, TypeError, ValueError):
                self.context._event("adapter_uninstall_failed", {})
        self._uninstallers.clear()
        self._stopped = True
        if self.capture_audit:
            type(self)._active_observers.discard(self)
        if self._monitoring_id is not None:
            monitoring = getattr(sys, "monitoring", None)
            if monitoring is not None:
                try:
                    monitoring.set_events(self._monitoring_id, monitoring.events.NO_EVENTS)
                    for event_name in ("PY_START", "PY_RETURN"):
                        event = getattr(monitoring.events, event_name, None)
                        if event is not None:
                            monitoring.register_callback(self._monitoring_id, event, None)
                    monitoring.free_tool_id(self._monitoring_id)
                except (AttributeError, RuntimeError, ValueError):
                    pass
            self._monitoring_id = None
        if self._previous_trace is not None or sys.gettrace() is not None:
            sys.settrace(self._previous_trace)
        if hasattr(threading, "settrace") and (self._previous_thread_trace is not None or threading.gettrace() is not None):
            threading.settrace(self._previous_thread_trace)

    def _capture_outputs(self) -> None:
        for source in self.capture_outputs:
            try:
                self.context.capture_file(source)
            except FileNotFoundError:
                self.context.boundary(
                    "missing_output",
                    target=str(source),
                    reason="configured automatic output was not present at run completion",
                    replay="not_available",
                )

    def _install_adapters(self) -> None:
        for adapter in self.adapters:
            try:
                uninstall = adapter.install(self.context)
            except (ImportError, OSError, RuntimeError, TypeError, ValueError) as error:
                self.context._event(
                    "adapter_install_failed",
                    {"name": getattr(adapter, "name", type(adapter).__name__), "error": str(error)},
                )
                continue
            if callable(uninstall):
                self._uninstallers.append(uninstall)

    def _register_audit_observer(self) -> None:
        with type(self)._audit_lock:
            if not type(self)._audit_installed:
                sys.addaudithook(type(self)._dispatch_audit)
                type(self)._audit_installed = True
            type(self)._active_observers.add(self)

    @classmethod
    def _dispatch_audit(cls, event: str, args: tuple[Any, ...]) -> None:
        for observer in list(cls._active_observers):
            observer._on_audit(event, args)

    def _on_audit(self, event: str, args: tuple[Any, ...]) -> None:
        if self._stopped or event not in type(self)._audit_events:
            return
        self._record(
            "runtime_audit",
            {
                "name": event,
                "args": safe_value(args, max_items=20, max_text=300),
            },
        )

    def _start_monitoring(self) -> bool:
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            return False
        try:
            for tool_id in range(6):
                if monitoring.get_tool(tool_id) is None:
                    monitoring.use_tool_id(tool_id, "runproof")
                    self._monitoring_id = tool_id
                    break
            if self._monitoring_id is None:
                return False
            py_start = monitoring.events.PY_START
            py_return = monitoring.events.PY_RETURN
            monitoring.register_callback(self._monitoring_id, py_start, self._on_py_start)
            if self.capture_returns:
                monitoring.register_callback(self._monitoring_id, py_return, self._on_py_return)
            events = py_start | (py_return if self.capture_returns else 0)
            monitoring.set_events(self._monitoring_id, events)
            self.context._event("observer_started", {"backend": "sys.monitoring"})
            return True
        except (AttributeError, RuntimeError, TypeError, ValueError):
            if self._monitoring_id is not None:
                try:
                    monitoring.free_tool_id(self._monitoring_id)
                except (AttributeError, RuntimeError, ValueError):
                    pass
                self._monitoring_id = None
            return False

    def _start_trace(self) -> None:
        self._previous_trace = sys.gettrace()
        self._previous_thread_trace = threading.gettrace() if hasattr(threading, "gettrace") else None
        sys.settrace(self._trace)
        if hasattr(threading, "settrace"):
            threading.settrace(self._trace)
        self.context._event("observer_started", {"backend": "sys.settrace"})

    def _source_details(self, filename: str, lineno: int, code_name: str) -> dict[str, Any]:
        return {
            "file": filename,
            "line": lineno,
            "function": code_name,
        }

    def _should_capture(self, filename: str) -> bool:
        try:
            path = Path(filename).expanduser().resolve()
        except (OSError, RuntimeError):
            return False
        if path == Path("<string>") or not path.is_file():
            return False
        if self._package_root in path.parents or path == self._package_root:
            return False
        if not self.include_stdlib and any(root in path.parents for root in self._stdlib_roots):
            return False
        if self.include_paths:
            return any(path == root or root in path.parents for root in self.include_paths)
        return True

    def _record(self, event: str, details: dict[str, Any]) -> None:
        if not self._stopped:
            self.context._event(event, details)

    def _on_py_start(self, code: Any, instruction_offset: int) -> None:
        filename = str(getattr(code, "co_filename", ""))
        if not self._should_capture(filename):
            return
        self._record(
            "python_call",
            {
                **self._source_details(filename, int(getattr(code, "co_firstlineno", 0)), str(getattr(code, "co_qualname", getattr(code, "co_name", "<code>")))),
                "instruction_offset": instruction_offset,
                "backend": "sys.monitoring",
            },
        )

    def _on_py_return(self, code: Any, instruction_offset: int, retval: Any) -> None:
        filename = str(getattr(code, "co_filename", ""))
        if not self._should_capture(filename):
            return
        self._record(
            "python_return",
            {
                **self._source_details(filename, int(getattr(code, "co_firstlineno", 0)), str(getattr(code, "co_qualname", getattr(code, "co_name", "<code>")))),
                "instruction_offset": instruction_offset,
                "return": summarize(retval),
                "backend": "sys.monitoring",
            },
        )

    def _trace(self, frame: FrameType, event: str, arg: Any) -> Any:
        if self._stopped:
            return None
        filename = frame.f_code.co_filename
        if not self._should_capture(filename):
            return self._trace
        details = self._source_details(
            filename,
            frame.f_lineno,
            getattr(frame.f_code, "co_qualname", getattr(frame.f_code, "co_name", "<code>")),
        )
        details["backend"] = "sys.settrace"
        if event == "call":
            self._record("python_call", details)
        elif event == "return" and self.capture_returns:
            details["return"] = summarize(arg)
            self._record("python_return", details)
        elif event == "exception":
            exception = arg[1] if isinstance(arg, tuple) and len(arg) > 1 else arg
            details["exception"] = {
                "type": f"{type(exception).__module__}.{type(exception).__qualname__}",
                "message": str(exception),
            }
            self._record("python_exception", safe_value(details))
        return self._trace


def auto_run(name: str, **kwargs: Any) -> AutoCapture:
    """Create a context manager that observes Python execution automatically."""
    capture_options = {
        key: kwargs.pop(key)
        for key in ("include_paths", "include_stdlib", "backend", "capture_returns", "capture_audit", "adapters", "capture_outputs")
        if key in kwargs
    }
    context = RunContext(name, **kwargs)
    return AutoCapture(context, **capture_options)
