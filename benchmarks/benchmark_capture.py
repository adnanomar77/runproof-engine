from __future__ import annotations

import json
import time
from pathlib import Path

from runproof_engine import auto_run


ROOT = Path(__file__).resolve().parent.parent


def workload(iterations: int) -> int:
    total = 0
    for value in range(iterations):
        total += (value * 3) % 97
    return total


def measure_plain(iterations: int, repeats: int) -> float:
    started = time.perf_counter()
    for _ in range(repeats):
        workload(iterations)
    return time.perf_counter() - started


def measure_auto(iterations: int, repeats: int, backend: str) -> dict[str, float]:
    started = time.perf_counter()
    with auto_run(
        "benchmark",
        root=ROOT / ".benchmark-runs",
        backend=backend,
        include_paths=[Path(__file__).resolve().parent],
        capture_audit=False,
        adapters=[],
    ):
        active_started = time.perf_counter()
        for _ in range(repeats):
            workload(iterations)
        active_seconds = time.perf_counter() - active_started
    return {"total_seconds": time.perf_counter() - started, "active_seconds": active_seconds}


def main() -> None:
    iterations = 20_000
    repeats = 5
    plain_seconds = measure_plain(iterations, repeats)
    measurements = {backend: measure_auto(iterations, repeats, backend) for backend in ("auto", "trace")}
    result = {
        "python": __import__("platform").python_version(),
        "iterations": iterations,
        "repeats": repeats,
        "plain_seconds": plain_seconds,
        "backends": {
            backend: {
                "active_seconds": measurement["active_seconds"],
                "total_seconds": measurement["total_seconds"],
                "active_overhead_ratio": measurement["active_seconds"] / plain_seconds if plain_seconds else None,
                "active_overhead_percent": ((measurement["active_seconds"] / plain_seconds) - 1) * 100 if plain_seconds else None,
            }
            for backend, measurement in measurements.items()
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
