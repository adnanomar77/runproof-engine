from __future__ import annotations

import csv
import dataclasses
import hashlib
import inspect
import json
import os
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

SECRET_MARKERS = (
    "secret",
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "authorization",
    "credential",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | os.PathLike[str], chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return sha256_bytes(canonical_json(safe_value(value, max_items=200)).encode("utf-8"))


def _redacted_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(marker in normalized for marker in SECRET_MARKERS)


def safe_value(value: Any, *, max_items: int = 100, max_text: int = 500) -> Any:
    """Return a bounded, JSON-safe representation without exposing likely secrets."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (str, Path)):
        text = str(value)
        return text if len(text) <= max_text else text[:max_text] + "…"
    if dataclasses.is_dataclass(value):
        return safe_value(dataclasses.asdict(value), max_items=max_items, max_text=max_text)
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        return {
            str(key): "[REDACTED]" if _redacted_key(key) else safe_value(item, max_items=max_items, max_text=max_text)
            for key, item in items
        }
    if isinstance(value, (list, tuple, set)):
        values = list(value)
        bounded = [safe_value(item, max_items=max_items, max_text=max_text) for item in values[:max_items]]
        if len(values) > max_items:
            bounded.append(f"… {len(values) - max_items} more items")
        return bounded
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return safe_value(value.to_dict(), max_items=max_items, max_text=max_text)
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
            pass
    if hasattr(value, "__dict__"):
        try:
            return {
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "attributes": safe_value(vars(value), max_items=max_items, max_text=max_text),
            }
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass
    return {
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "repr": str(value)[:max_text],
    }


def summarize(value: Any) -> dict[str, Any]:
    """Describe a runtime value without serializing an unbounded payload."""
    summary: dict[str, Any] = {
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "fingerprint": fingerprint(value),
    }
    if value is None or isinstance(value, (bool, int, float, str)):
        summary["value"] = safe_value(value)
    elif isinstance(value, (list, tuple, set, dict)):
        summary["length"] = len(value)
        if isinstance(value, dict):
            summary["keys"] = [str(key) for key in list(value.keys())[:100]]
    else:
        for attribute in ("shape", "columns", "dtypes", "size"):
            if hasattr(value, attribute):
                try:
                    summary[attribute] = safe_value(getattr(value, attribute))
                except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
                    pass
    return summary


def function_descriptor(function: Any) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "module": getattr(function, "__module__", None),
        "qualname": getattr(function, "__qualname__", repr(function)),
    }
    try:
        source = inspect.getsource(function)
        descriptor["source_sha256"] = sha256_bytes(source.encode("utf-8"))
    except (OSError, TypeError):
        descriptor["source_sha256"] = None
    return descriptor


def environment_snapshot() -> dict[str, Any]:
    packages: list[dict[str, str]] = []
    try:
        for distribution in metadata.distributions():
            name = distribution.metadata.get("Name")
            version = distribution.version
            if name and version:
                packages.append({"name": name.lower(), "version": version})
        packages.sort(key=lambda item: item["name"])
    except (ImportError, OSError, RuntimeError, ValueError):
        packages = []
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": packages,
    }


def _tabular_metadata(file_path: Path) -> dict[str, Any]:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                columns = next(reader, [])
                rows = sum(1 for _ in reader)
            return {"rows": rows, "columns": columns, "schema": {column: "unknown" for column in columns}}
        except (UnicodeDecodeError, csv.Error):
            return {}
    if suffix == ".jsonl":
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                rows = sum(1 for line in handle if line.strip())
            return {"rows": rows}
        except UnicodeDecodeError:
            return {}
    return {}


def file_metadata(path: str | os.PathLike[str], *, copy_path: str | None = None) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    metadata_record: dict[str, Any] = {
        "path": str(file_path),
        "name": file_path.name,
        "size_bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path),
    }
    metadata_record.update(_tabular_metadata(file_path))
    if copy_path:
        metadata_record["captured_copy"] = copy_path
    return metadata_record


def write_json(path: str | os.PathLike[str], value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def read_json(path: str | os.PathLike[str]) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
