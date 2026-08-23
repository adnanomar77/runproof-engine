from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .utils import safe_value


@dataclass
class Difference:
    area: str
    path: str
    kind: str
    before: Any
    after: Any
    explanation: str
    confidence: str = "evidence"

    def to_dict(self) -> dict[str, Any]:
        return {
            "area": self.area,
            "path": self.path,
            "kind": self.kind,
            "before": safe_value(self.before),
            "after": safe_value(self.after),
            "explanation": self.explanation,
            "confidence": self.confidence,
        }


@dataclass
class RunDiff:
    left_run_id: str
    right_run_id: str
    differences: list[Difference] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return not self.differences

    @property
    def first_divergent_step(self) -> str | None:
        for difference in self.differences:
            if difference.area == "steps":
                return difference.path.split(".")[0]
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_run_id": self.left_run_id,
            "right_run_id": self.right_run_id,
            "identical": self.identical,
            "first_divergent_step": self.first_divergent_step,
            "differences": [difference.to_dict() for difference in self.differences],
        }

    def render(self) -> str:
        if self.identical:
            return f"Runs {self.left_run_id} and {self.right_run_id} are observably identical."
        lines = [
            f"Run diff: {self.left_run_id} -> {self.right_run_id}",
            f"Differences: {len(self.differences)}",
        ]
        if self.first_divergent_step:
            lines.append(f"First divergent step: {self.first_divergent_step}")
        for difference in self.differences:
            lines.append(
                f"- [{difference.area}] {difference.path}: {difference.explanation} "
                f"(confidence={difference.confidence})"
            )
        return "\n".join(lines)


def compare_manifests(left: dict[str, Any], right: dict[str, Any]) -> RunDiff:
    left_run = left.get("run", {})
    right_run = right.get("run", {})
    result = RunDiff(
        left_run_id=str(left_run.get("run_id", "unknown")),
        right_run_id=str(right_run.get("run_id", "unknown")),
    )
    _compare_inputs(left.get("inputs", []), right.get("inputs", []), result)
    _compare_steps(left.get("steps", []), right.get("steps", []), result)
    _compare_outputs(left.get("outputs", []), right.get("outputs", []), result)
    _compare_checks(left.get("checks", []), right.get("checks", []), result)
    _compare_environment(left.get("environment"), right.get("environment"), result)
    if left_run.get("status") != right_run.get("status"):
        result.differences.append(Difference(
            area="run",
            path="status",
            kind="changed",
            before=left_run.get("status"),
            after=right_run.get("status"),
            explanation="run status changed",
        ))
    return result


def _index(records: list[dict[str, Any]], key: str = "name") -> dict[str, dict[str, Any]]:
    return {str(item.get(key, index)): item for index, item in enumerate(records)}


def _compare_inputs(left: list[dict[str, Any]], right: list[dict[str, Any]], result: RunDiff) -> None:
    left_map, right_map = _index(left), _index(right)
    for name in sorted(set(left_map) | set(right_map)):
        if name not in left_map:
            result.differences.append(Difference("inputs", name, "added", None, right_map[name], "input was added"))
            continue
        if name not in right_map:
            result.differences.append(Difference("inputs", name, "removed", left_map[name], None, "input was removed"))
            continue
        before, after = left_map[name], right_map[name]
        if before.get("sha256") != after.get("sha256"):
            result.differences.append(Difference(
                "inputs", f"{name}.sha256", "changed", before.get("sha256"), after.get("sha256"),
                "input content changed according to its SHA-256 fingerprint",
            ))
        for field_name in ("size_bytes", "rows", "columns", "schema"):
            if before.get(field_name) != after.get(field_name) and (field_name in before or field_name in after):
                result.differences.append(Difference(
                    "inputs", f"{name}.{field_name}", "changed", before.get(field_name), after.get(field_name),
                    f"input metadata field '{field_name}' changed",
                ))


def _compare_steps(left: list[dict[str, Any]], right: list[dict[str, Any]], result: RunDiff) -> None:
    left_map, right_map = _index(left), _index(right)
    for name in sorted(set(left_map) | set(right_map)):
        if name not in left_map:
            result.differences.append(Difference("steps", name, "added", None, right_map[name], "step was added"))
            continue
        if name not in right_map:
            result.differences.append(Difference("steps", name, "removed", left_map[name], None, "step was removed"))
            continue
        before, after = left_map[name], right_map[name]
        if before.get("status") != after.get("status"):
            result.differences.append(Difference("steps", f"{name}.status", "changed", before.get("status"), after.get("status"), "step status changed"))
        before_output = (before.get("output") or {}).get("fingerprint")
        after_output = (after.get("output") or {}).get("fingerprint")
        if before_output != after_output:
            result.differences.append(Difference(
                "steps", f"{name}.output.fingerprint", "changed", before_output, after_output,
                "step output changed; downstream artifacts may be affected",
            ))
        before_function = (before.get("function") or {}).get("source_sha256")
        after_function = (after.get("function") or {}).get("source_sha256")
        if before_function != after_function:
            result.differences.append(Difference(
                "steps", f"{name}.function.source_sha256", "changed", before_function, after_function,
                "step source fingerprint changed",
            ))


def _compare_outputs(left: list[dict[str, Any]], right: list[dict[str, Any]], result: RunDiff) -> None:
    left_map, right_map = _index(left), _index(right)
    for name in sorted(set(left_map) | set(right_map)):
        if name not in left_map:
            result.differences.append(Difference("outputs", name, "added", None, right_map[name], "output was added"))
        elif name not in right_map:
            result.differences.append(Difference("outputs", name, "removed", left_map[name], None, "output was removed"))
        elif left_map[name].get("sha256") != right_map[name].get("sha256"):
            result.differences.append(Difference(
                "outputs", f"{name}.sha256", "changed", left_map[name].get("sha256"), right_map[name].get("sha256"),
                "artifact content changed",
            ))


def _compare_checks(left: list[dict[str, Any]], right: list[dict[str, Any]], result: RunDiff) -> None:
    left_map, right_map = _index(left), _index(right)
    for name in sorted(set(left_map) | set(right_map)):
        if name not in left_map or name not in right_map:
            result.differences.append(Difference("checks", name, "changed", left_map.get(name), right_map.get(name), "check set changed"))
        elif left_map[name].get("passed") != right_map[name].get("passed"):
            result.differences.append(Difference(
                "checks", f"{name}.passed", "changed", left_map[name].get("passed"), right_map[name].get("passed"),
                "check outcome changed",
            ))


def _compare_environment(left: dict[str, Any] | None, right: dict[str, Any] | None, result: RunDiff) -> None:
    if left is None or right is None:
        if left != right:
            result.differences.append(Difference("environment", "snapshot", "changed", bool(left), bool(right), "environment snapshot availability changed"))
        return
    for field_name in ("python_version", "platform", "machine"):
        if left.get(field_name) != right.get(field_name):
            result.differences.append(Difference(
                "environment", field_name, "changed", left.get(field_name), right.get(field_name),
                f"environment field '{field_name}' changed",
            ))
    left_packages = {item.get("name"): item.get("version") for item in left.get("packages", [])}
    right_packages = {item.get("name"): item.get("version") for item in right.get("packages", [])}
    for name in sorted(set(left_packages) | set(right_packages)):
        if left_packages.get(name) != right_packages.get(name):
            result.differences.append(Difference(
                "environment", f"packages.{name}", "changed", left_packages.get(name), right_packages.get(name),
                "installed package version changed",
            ))
