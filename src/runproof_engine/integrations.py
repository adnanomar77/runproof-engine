"""Optional real-library adapters for automatic RunProof evidence capture.

Adapters are best-effort observers. They record stable metadata and hashes,
avoid consuming streaming responses, and mark external state as a boundary when
it cannot be snapshotted safely.
"""

from __future__ import annotations

import functools
import hashlib
import sqlite3
import subprocess  # nosec B404 - observer wraps caller-provided subprocess.run without shell execution
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .adapters import AdapterInfo, _safe_url
from .core import RunContext
from .utils import safe_value, summarize

_SECRET_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie"}


def _safe_headers(headers: Any) -> dict[str, Any]:
    try:
        items = headers.items()
    except AttributeError:
        return {}
    return {
        str(key): "[REDACTED]" if str(key).lower() in _SECRET_HEADERS else str(value)
        for key, value in items
    }


def _path_value(value: Any) -> Path | None:
    if isinstance(value, (str, Path)):
        return Path(value).expanduser().resolve()
    return None


def _patch(target: Any, name: str, replacement: Callable[..., Any], originals: list[tuple[Any, str, Any]]) -> None:
    original = getattr(target, name)
    originals.append((target, name, original))
    setattr(target, name, replacement)


def _restore(originals: list[tuple[Any, str, Any]]) -> None:
    for target, name, original in reversed(originals):
        setattr(target, name, original)


def _record_file_input(context: RunContext, path: Path, label: str) -> None:
    if path.is_file():
        try:
            context.input(path, name=label)
        except (OSError, ValueError):
            context._event("adapter_input_failed", {"adapter": label, "path": str(path)})


def _record_file_output(context: RunContext, path: Path, label: str) -> None:
    if path.is_file():
        try:
            context.capture_file(path, name=label)
        except (OSError, ValueError):
            context._event("adapter_output_failed", {"adapter": label, "path": str(path)})
    else:
        context.boundary(
            "missing_adapter_output",
            target=str(path),
            reason=f"{label} returned before the expected output file existed",
            replay="not_available",
        )


class PandasAdapter:
    name = "pandas"
    info = AdapterInfo("pandas", "1", ("dataframe-input", "dataframe-output", "file-hashes"))

    def install(self, context: RunContext) -> Callable[[], None]:
        import pandas as pd

        originals: list[tuple[Any, str, Any]] = []
        for function_name in ("read_csv", "read_json", "read_parquet"):
            if not hasattr(pd, function_name):
                continue
            original = getattr(pd, function_name)

            @functools.wraps(original)
            def read_wrapper(*args: Any, _original: Any = original, _name: str = function_name, **kwargs: Any) -> Any:
                result = _original(*args, **kwargs)
                path = _path_value(args[0] if args else kwargs.get("path_or_buf") or kwargs.get("path"))
                if path:
                    _record_file_input(context, path, f"pandas.{_name}")
                context._event("dataframe_read", {"adapter": "pandas", "operation": _name, "summary": summarize(result)})
                return result

            _patch(pd, function_name, read_wrapper, originals)

        dataframe = pd.DataFrame
        for method_name in ("to_csv", "to_json", "to_parquet"):
            if not hasattr(dataframe, method_name):
                continue
            original = getattr(dataframe, method_name)

            @functools.wraps(original)
            def write_wrapper(self: Any, *args: Any, _original: Any = original, _name: str = method_name, **kwargs: Any) -> Any:
                result = _original(self, *args, **kwargs)
                path = _path_value(args[0] if args else kwargs.get("path_or_buf") or kwargs.get("path"))
                if path:
                    _record_file_output(context, path, f"pandas.{_name}")
                context._event("dataframe_written", {"adapter": "pandas", "operation": _name, "summary": summarize(self)})
                return result

            _patch(dataframe, method_name, write_wrapper, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class PolarsAdapter:
    name = "polars"
    info = AdapterInfo("polars", "1", ("dataframe-input", "dataframe-output", "file-hashes"))

    def install(self, context: RunContext) -> Callable[[], None]:
        import polars as pl

        originals: list[tuple[Any, str, Any]] = []
        for function_name in ("read_csv", "read_parquet", "read_ndjson"):
            if not hasattr(pl, function_name):
                continue
            original = getattr(pl, function_name)

            @functools.wraps(original)
            def read_wrapper(*args: Any, _original: Any = original, _name: str = function_name, **kwargs: Any) -> Any:
                result = _original(*args, **kwargs)
                path = _path_value(args[0] if args else kwargs.get("source"))
                if path:
                    _record_file_input(context, path, f"polars.{_name}")
                context._event("dataframe_read", {"adapter": "polars", "operation": _name, "summary": summarize(result)})
                return result

            _patch(pl, function_name, read_wrapper, originals)

        for method_name in ("write_csv", "write_parquet", "write_ndjson"):
            original = getattr(pl.DataFrame, method_name, None)
            if original is None:
                continue

            @functools.wraps(original)
            def write_wrapper(self: Any, *args: Any, _original: Any = original, _name: str = method_name, **kwargs: Any) -> Any:
                result = _original(self, *args, **kwargs)
                path = _path_value(args[0] if args else kwargs.get("file"))
                if path:
                    _record_file_output(context, path, f"polars.{_name}")
                context._event("dataframe_written", {"adapter": "polars", "operation": _name, "summary": summarize(self)})
                return result

            _patch(pl.DataFrame, method_name, write_wrapper, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class RequestsAdapter:
    name = "requests"
    info = AdapterInfo("requests", "1", ("request-metadata", "response-status", "secret-redaction"))

    def install(self, context: RunContext) -> Callable[[], None]:
        import requests

        originals: list[tuple[Any, str, Any]] = []
        original = requests.sessions.Session.request

        @functools.wraps(original)
        def wrapped(session: Any, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
            response = original(session, method, url, *args, **kwargs)
            request = getattr(response, "request", None)
            context._event(
                "http_request_observed",
                {
                    "adapter": self.name,
                    "method": str(method).upper(),
                    "url": _safe_url(str(url)),
                    "headers": _safe_headers(getattr(request, "headers", None)),
                    "status_code": getattr(response, "status_code", None),
                    "stream": bool(kwargs.get("stream", False)),
                },
            )
            context.boundary(
                "network_response",
                target=_safe_url(str(url)),
                reason="requests response body is not archived automatically; streaming semantics are preserved",
                replay="requires_live_service",
            )
            return response

        _patch(requests.sessions.Session, "request", wrapped, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class HTTPXAdapter:
    name = "httpx"
    info = AdapterInfo("httpx", "1", ("sync-hooks", "async-hooks", "response-status", "secret-redaction"))

    def install(self, context: RunContext) -> Callable[[], None]:
        import httpx

        originals: list[tuple[Any, str, Any]] = []
        client_original = httpx.Client.__init__
        async_original = httpx.AsyncClient.__init__

        def record_request(request: Any) -> None:
            context._event(
                "http_request_prepared",
                {
                    "adapter": self.name,
                    "method": str(request.method),
                    "url": _safe_url(str(request.url)),
                    "headers": _safe_headers(request.headers),
                },
            )

        def record_response(response: Any) -> None:
            request = response.request
            url = _safe_url(str(request.url))
            context._event(
                "http_request_observed",
                {"adapter": self.name, "method": str(request.method), "url": url, "status_code": response.status_code},
            )
            context.boundary(
                "network_response",
                target=url,
                reason="HTTPX response hook does not read the body automatically, preserving streaming semantics",
                replay="requires_live_service",
            )

        @functools.wraps(client_original)
        def client_init(client: Any, *args: Any, **kwargs: Any) -> None:
            hooks = dict(kwargs.get("event_hooks") or {})
            hooks["request"] = [record_request, *list(hooks.get("request", []))]
            hooks["response"] = [record_response, *list(hooks.get("response", []))]
            kwargs["event_hooks"] = hooks
            client_original(client, *args, **kwargs)

        async def async_record_request(request: Any) -> None:
            record_request(request)

        async def async_record_response(response: Any) -> None:
            record_response(response)

        @functools.wraps(async_original)
        def async_init(client: Any, *args: Any, **kwargs: Any) -> None:
            hooks = dict(kwargs.get("event_hooks") or {})
            hooks["request"] = [async_record_request, *list(hooks.get("request", []))]
            hooks["response"] = [async_record_response, *list(hooks.get("response", []))]
            kwargs["event_hooks"] = hooks
            async_original(client, *args, **kwargs)

        _patch(httpx.Client, "__init__", client_init, originals)
        _patch(httpx.AsyncClient, "__init__", async_init, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class SQLiteAdapter:
    name = "sqlite3"
    info = AdapterInfo("sqlite3", "1", ("sql-statements", "database-path", "state-boundary"))

    def install(self, context: RunContext) -> Callable[[], None]:
        originals: list[tuple[Any, str, Any]] = []
        original = sqlite3.connect

        def wrapped(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            connection = original(*args, **kwargs)
            database = _path_value(args[0] if args else kwargs.get("database"))
            target = str(database) if database else ":memory:"
            if database and database.is_file():
                _record_file_input(context, database, "sqlite3.database")
            context.boundary(
                "database_state",
                target=target,
                reason="SQLite adapter records statements but does not snapshot the complete database transaction state",
                replay="requires_database_snapshot",
            )

            def trace(statement: str) -> None:
                context._event("sql_query", {"adapter": self.name, "database": target, "statement": statement[:2000]})

            connection.set_trace_callback(trace)
            return connection

        _patch(sqlite3, "connect", wrapped, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class PsycopgAdapter:
    name = "psycopg"
    info = AdapterInfo("psycopg", "1", ("sql-statements", "parameter-summary", "database-state-boundary"))

    def install(self, context: RunContext) -> Callable[[], None]:
        import psycopg

        originals: list[tuple[Any, str, Any]] = []
        cursor_class = getattr(psycopg, "Cursor", None)
        original = getattr(cursor_class, "execute", None) if cursor_class is not None else None
        if original is None:
            raise ImportError("psycopg Cursor.execute is unavailable")

        @functools.wraps(original)
        def wrapped(cursor: Any, query: Any, params: Any = None, *args: Any, **kwargs: Any) -> Any:
            result = original(cursor, query, params, *args, **kwargs)
            context._event(
                "sql_query",
                {"adapter": self.name, "database": "postgresql", "statement": str(query)[:2000], "parameters": safe_value(params)},
            )
            context.boundary(
                "database_state",
                target="postgresql",
                reason="PostgreSQL transaction and server state are not snapshotted automatically",
                replay="requires_database_snapshot",
            )
            return result

        _patch(cursor_class, "execute", wrapped, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class SQLAlchemyAdapter:
    name = "sqlalchemy"
    info = AdapterInfo("sqlalchemy", "1", ("sql-statements", "engine-events", "database-state-boundary"))

    def install(self, context: RunContext) -> Callable[[], None]:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        def before_cursor_execute(connection: Any, cursor: Any, statement: str, parameters: Any, _context: Any, _executemany: bool) -> None:
            dialect = getattr(getattr(connection, "dialect", None), "name", "database")
            context._event(
                "sql_query",
                {"adapter": self.name, "database": dialect, "statement": str(statement)[:2000], "parameters": safe_value(parameters)},
            )
            context.boundary(
                "database_state",
                target=str(dialect),
                reason="SQLAlchemy adapter records cursor operations but does not snapshot complete database state",
                replay="requires_database_snapshot",
            )

        event.listen(Engine, "before_cursor_execute", before_cursor_execute)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: event.remove(Engine, "before_cursor_execute", before_cursor_execute)


class SubprocessAdapter:
    name = "subprocess"
    info = AdapterInfo("subprocess", "1", ("command-metadata", "return-code", "process-boundary"))

    def install(self, context: RunContext) -> Callable[[], None]:
        originals: list[tuple[Any, str, Any]] = []
        original = subprocess.run

        @functools.wraps(original)
        def wrapped(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
            command = args[0] if args else kwargs.get("args")
            result = original(*args, **kwargs)
            stdout = getattr(result, "stdout", None)
            stderr = getattr(result, "stderr", None)
            context._event(
                "subprocess_completed",
                {
                    "adapter": self.name,
                    "args": safe_value(command),
                    "returncode": result.returncode,
                    "stdout_sha256": hashlib.sha256(stdout if isinstance(stdout, bytes) else str(stdout).encode("utf-8")).hexdigest() if stdout is not None else None,
                    "stderr_sha256": hashlib.sha256(stderr if isinstance(stderr, bytes) else str(stderr).encode("utf-8")).hexdigest() if stderr is not None else None,
                },
            )
            context.boundary(
                "subprocess_state",
                target=str(safe_value(command)),
                reason="subprocess environment and side effects are outside the Python artifact",
                replay="requires_process_environment",
            )
            return result

        _patch(subprocess, "run", wrapped, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class Boto3Adapter:
    name = "boto3"
    info = AdapterInfo("boto3", "1", ("service-operation", "parameter-redaction", "object-storage-boundary"))

    def install(self, context: RunContext) -> Callable[[], None]:
        import botocore.client

        originals: list[tuple[Any, str, Any]] = []
        target = botocore.client.BaseClient
        original = target._make_api_call

        @functools.wraps(original)
        def wrapped(client: Any, operation_name: str, api_params: Any) -> Any:
            response = original(client, operation_name, api_params)
            service = getattr(client, "_service_model", None)
            service_name = getattr(service, "service_name", "aws")
            context._event(
                "cloud_api_call",
                {
                    "adapter": self.name,
                    "service": service_name,
                    "operation": operation_name,
                    "parameters": safe_value(api_params),
                    "response_summary": summarize(response),
                },
            )
            context.boundary(
                "cloud_service_state",
                target=f"{service_name}:{operation_name}",
                reason="cloud service state and object versions are not snapshotted automatically",
                replay="requires_live_service",
            )
            return response

        _patch(target, "_make_api_call", wrapped, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class JupyterAdapter:
    name = "jupyter"
    info = AdapterInfo("jupyter", "1", ("notebook-execution", "cell-boundary"))

    def install(self, context: RunContext) -> Callable[[], None]:
        from nbclient import NotebookClient

        originals: list[tuple[Any, str, Any]] = []
        original = NotebookClient.execute

        @functools.wraps(original)
        def wrapped(client: Any, *args: Any, **kwargs: Any) -> Any:
            context._event("notebook_execution_started", {"adapter": self.name, "cells": len(getattr(client.nb, "cells", []))})
            result = original(client, *args, **kwargs)
            context._event("notebook_execution_completed", {"adapter": self.name, "cells": len(getattr(client.nb, "cells", []))})
            context.boundary(
                "notebook_kernel_state",
                target="jupyter-kernel",
                reason="kernel state and external notebook effects are not fully captured",
                replay="requires_kernel_environment",
            )
            return result

        _patch(NotebookClient, "execute", wrapped, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class TorchAdapter:
    name = "torch"
    info = AdapterInfo("torch", "1", ("model-save-load", "file-hashes", "device-boundary"))

    def install(self, context: RunContext) -> Callable[[], None]:
        import torch

        originals: list[tuple[Any, str, Any]] = []
        for function_name in ("save", "load"):
            original = getattr(torch, function_name, None)
            if original is None:
                continue

            @functools.wraps(original)
            def wrapped(*args: Any, _original: Any = original, _name: str = function_name, **kwargs: Any) -> Any:
                result = _original(*args, **kwargs)
                path = _path_value(args[1] if _name == "save" and len(args) > 1 else args[0] if args else None)
                if path and _name == "save":
                    _record_file_output(context, path, "torch.save")
                elif path and _name == "load":
                    _record_file_input(context, path, "torch.load")
                context._event("ml_artifact_operation", {"adapter": self.name, "operation": _name, "path": str(path) if path else None})
                if _name == "load":
                    context.boundary("device_state", target=str(path) if path else "torch", reason="tensor device and native runtime state may differ", replay="requires_matching_device")
                return result

            _patch(torch, function_name, wrapped, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


class JoblibAdapter:
    name = "joblib"
    info = AdapterInfo("joblib", "1", ("model-save-load", "file-hashes"))

    def install(self, context: RunContext) -> Callable[[], None]:
        import joblib

        originals: list[tuple[Any, str, Any]] = []
        for function_name in ("dump", "load"):
            original = getattr(joblib, function_name)

            @functools.wraps(original)
            def wrapped(*args: Any, _original: Any = original, _name: str = function_name, **kwargs: Any) -> Any:
                result = _original(*args, **kwargs)
                path = _path_value(args[1] if _name == "dump" and len(args) > 1 else args[0] if args else None)
                if path and _name == "dump":
                    _record_file_output(context, path, "joblib.dump")
                elif path and _name == "load":
                    _record_file_input(context, path, "joblib.load")
                context._event("ml_artifact_operation", {"adapter": self.name, "operation": _name, "path": str(path) if path else None})
                return result

            _patch(joblib, function_name, wrapped, originals)
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})
        return lambda: _restore(originals)


def available_adapters() -> tuple[Any, ...]:
    """Return optional adapters whose dependencies can be imported safely."""
    candidates = (
        PandasAdapter,
        PolarsAdapter,
        RequestsAdapter,
        HTTPXAdapter,
        SQLiteAdapter,
        SubprocessAdapter,
        Boto3Adapter,
        JupyterAdapter,
        JoblibAdapter,
        PsycopgAdapter,
        SQLAlchemyAdapter,
        TorchAdapter,
    )
    available: list[Any] = []
    module_names = {
        PandasAdapter: "pandas",
        PolarsAdapter: "polars",
        RequestsAdapter: "requests",
        HTTPXAdapter: "httpx",
        SQLiteAdapter: "sqlite3",
        SubprocessAdapter: "subprocess",
        Boto3Adapter: "boto3",
        JupyterAdapter: "nbclient",
        JoblibAdapter: "joblib",
        PsycopgAdapter: "psycopg",
        SQLAlchemyAdapter: "sqlalchemy",
        TorchAdapter: "torch",
    }
    import importlib.util

    for adapter_class in candidates:
        if importlib.util.find_spec(module_names[adapter_class]) is not None:
            available.append(adapter_class())
    return tuple(available)


__all__ = [
    "Boto3Adapter",
    "HTTPXAdapter",
    "JoblibAdapter",
    "JupyterAdapter",
    "PandasAdapter",
    "PolarsAdapter",
    "PsycopgAdapter",
    "RequestsAdapter",
    "SQLAlchemyAdapter",
    "SQLiteAdapter",
    "SubprocessAdapter",
    "TorchAdapter",
    "available_adapters",
]
