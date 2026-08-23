"""Environment lock and reconstruction planning for RunProof."""

from __future__ import annotations

import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from .utils import fingerprint, read_json, write_json

LOCK_SCHEMA_VERSION = "0.1"


def package_inventory() -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if name and version:
            packages.append({"name": name.lower().replace("_", "-"), "version": version})
    return sorted(packages, key=lambda item: (item["name"], item["version"]))


def environment_lock(*, root: str | Path | None = None) -> dict[str, Any]:
    """Create a deterministic, reviewable lock description for the current interpreter."""
    lock: dict[str, Any] = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "packages": package_inventory(),
        "reconstruction": {
            "requires_os_match": True,
            "requires_python_implementation_match": True,
            "requires_external_services": False,
            "note": "Package versions are captured; OS, hardware, native libraries, data, and external service state still require separate evidence.",
        },
    }
    lock["lock_fingerprint"] = fingerprint(lock)
    if root is not None:
        write_json(Path(root) / "environment.lock.json", lock)
    return lock


def compare_environment_lock(lock: dict[str, Any]) -> dict[str, Any]:
    current = environment_lock()
    expected_packages = {item["name"]: item["version"] for item in lock.get("packages", [])}
    current_packages = {item["name"]: item["version"] for item in current.get("packages", [])}
    changed = {
        "added": sorted(set(current_packages) - set(expected_packages)),
        "removed": sorted(set(expected_packages) - set(current_packages)),
        "version_changed": sorted(
            name for name in set(expected_packages) & set(current_packages)
            if expected_packages[name] != current_packages[name]
        ),
    }
    expected_python = lock.get("python", {})
    python_match = (
        expected_python.get("version") == current["python"].get("version")
        and expected_python.get("implementation") == current["python"].get("implementation")
    )
    platform_match = lock.get("platform", {}).get("system") == current["platform"].get("system")
    return {
        "lock_fingerprint": lock.get("lock_fingerprint"),
        "current_fingerprint": current.get("lock_fingerprint"),
        "python_match": python_match,
        "platform_match": platform_match,
        "packages": changed,
        "match": python_match and platform_match and not any(changed.values()),
    }


def reconstruction_plan(lock: dict[str, Any], *, python_executable: str = "python") -> dict[str, Any]:
    """Return commands for a human- or CI-approved reconstruction; never executes them."""
    packages = [f"{item['name']}=={item['version']}" for item in lock.get("packages", [])]
    command = [python_executable, "-m", "pip", "install", *packages]
    return {
        "safe_to_execute": False,
        "approval_required": True,
        "commands": [command],
        "package_count": len(packages),
        "note": "Review the lock, index, hashes, native wheels, OS, and security policy before executing.",
    }


def write_environment_lock(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, environment_lock())
    return target


def load_environment_lock(path: str | Path) -> dict[str, Any]:
    payload = read_json(Path(path))
    if payload.get("schema_version") != LOCK_SCHEMA_VERSION:
        raise ValueError(f"unsupported environment lock schema: {payload.get('schema_version')}")
    return payload


__all__ = [
    "LOCK_SCHEMA_VERSION",
    "compare_environment_lock",
    "environment_lock",
    "load_environment_lock",
    "package_inventory",
    "reconstruction_plan",
    "write_environment_lock",
]
