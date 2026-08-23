from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .diff import RunDiff, compare_manifests
from .environment import compare_environment_lock, reconstruction_plan
from .provenance import ProvenanceGraph
from .utils import file_metadata, read_json, sha256_file


@dataclass
class ReplayReport:
    status: str
    run_id: str
    mode: str
    reasons: list[str] = field(default_factory=list)
    compared_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "mode": self.mode,
            "reasons": self.reasons,
            "compared_run_id": self.compared_run_id,
        }

    def __str__(self) -> str:
        suffix = f"; reasons={self.reasons}" if self.reasons else ""
        return f"ReplayReport(status={self.status!r}, run_id={self.run_id!r}, mode={self.mode!r}{suffix})"


class LoadedRun:
    def __init__(self, artifact_dir: str | os.PathLike[str]) -> None:
        self.artifact_dir = Path(artifact_dir).expanduser().resolve()
        self.manifest_path = self.artifact_dir / "manifest.json"
        if not self.manifest_path.is_file():
            raise FileNotFoundError(f"RunProof manifest not found: {self.manifest_path}")
        self.manifest = read_json(self.manifest_path)

    @property
    def run_id(self) -> str:
        return str(self.manifest.get("run", {}).get("run_id", self.artifact_dir.name))

    @property
    def name(self) -> str:
        return str(self.manifest.get("run", {}).get("name", self.artifact_dir.parent.name))

    @property
    def status(self) -> str:
        return str(self.manifest.get("run", {}).get("status", "unknown"))

    @property
    def provenance(self) -> ProvenanceGraph:
        graph_path = self.artifact_dir / "provenance.json"
        if graph_path.is_file():
            return ProvenanceGraph.from_dict(read_json(graph_path))
        return ProvenanceGraph.from_manifest(self.manifest)

    def environment_comparison(self) -> dict[str, Any]:
        lock_path = self.artifact_dir / "environment" / "environment.lock.json"
        if not lock_path.is_file():
            return {"match": False, "reason": "environment lock is missing"}
        return compare_environment_lock(read_json(lock_path))

    def reconstruction_plan(self, *, python_executable: str = "python") -> dict[str, Any]:
        lock_path = self.artifact_dir / "environment" / "environment.lock.json"
        if not lock_path.is_file():
            raise FileNotFoundError(f"environment lock not found: {lock_path}")
        return reconstruction_plan(read_json(lock_path), python_executable=python_executable)

    def verify_integrity(self) -> ReplayReport:
        reasons: list[str] = []
        for record in self.manifest.get("inputs", []):
            source = Path(record.get("path", ""))
            if source.is_file():
                if file_metadata(source).get("sha256") != record.get("sha256"):
                    reasons.append(f"input changed: {record.get('name', source.name)}")
                continue
            captured = record.get("captured_copy")
            captured_path = (self.artifact_dir / captured).resolve() if captured else None
            if captured_path and captured_path.is_file() and file_metadata(captured_path).get("sha256") == record.get("sha256"):
                continue
            reasons.append(f"input missing: {source}")
        for record in self.manifest.get("outputs", []):
            output = (self.artifact_dir / record.get("path", "")).resolve()
            if not output.is_file():
                reasons.append(f"output missing: {output}")
            elif file_metadata(output).get("sha256") != record.get("sha256"):
                reasons.append(f"artifact changed: {record.get('name', output.name)}")
        integrity_file = self.artifact_dir / "integrity.json"
        if integrity_file.is_file():
            try:
                integrity = read_json(integrity_file)
                for record in integrity.get("files", []):
                    artifact = (self.artifact_dir / record["path"]).resolve()
                    if not artifact.is_file():
                        reasons.append(f"integrity file missing: {record['path']}")
                    elif sha256_file(artifact) != record.get("sha256"):
                        reasons.append(f"integrity mismatch: {record['path']}")
            except (KeyError, TypeError, ValueError):
                reasons.append("integrity manifest is invalid")
        if reasons:
            status = "non_reproducible"
        elif self.manifest.get("boundaries"):
            status = "verified_with_boundaries"
        else:
            status = "verified"
        return ReplayReport(status=status, run_id=self.run_id, mode="integrity", reasons=reasons)

    def replay(
        self,
        *,
        mode: str = "strict",
        runner: Callable[[LoadedRun], str | os.PathLike[str] | LoadedRun] | None = None,
    ) -> ReplayReport:
        """Validate replay prerequisites and optionally compare a user-supplied re-execution.

        RunProof does not guess how to reconstruct arbitrary Python state. A runner is
        required to execute the original workflow again; without it, strict mode only
        verifies captured evidence and reports that no new execution was performed.
        """
        if mode not in {"strict", "fresh"}:
            raise ValueError("mode must be 'strict' or 'fresh'")
        if runner is None:
            integrity = self.verify_integrity()
            if integrity.status != "verified":
                integrity.mode = mode
                return integrity
            return ReplayReport(
                status="replay_ready",
                run_id=self.run_id,
                mode=mode,
                reasons=["integrity verified; pass runner=... to execute and compare the workflow"],
            )
        new_artifact = runner(self)
        other = new_artifact if isinstance(new_artifact, LoadedRun) else load_run(new_artifact)
        comparison = self.diff(other)
        return ReplayReport(
            status="verified" if comparison.identical else "non_reproducible",
            run_id=self.run_id,
            mode=mode,
            reasons=[] if comparison.identical else [difference.explanation for difference in comparison.differences],
            compared_run_id=other.run_id,
        )

    def diff(self, other: LoadedRun | str | os.PathLike[str]) -> RunDiff:
        other_run = other if isinstance(other, LoadedRun) else load_run(other)
        return compare_manifests(self.manifest, other_run.manifest)


def load_run(artifact_dir: str | os.PathLike[str]) -> LoadedRun:
    return LoadedRun(artifact_dir)
