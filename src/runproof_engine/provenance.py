"""Content-addressed provenance graph for RunProof artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .utils import fingerprint, safe_value


@dataclass
class ProvenanceNode:
    node_id: str
    kind: str
    label: str
    digest: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "digest": self.digest,
            "attributes": safe_value(self.attributes),
        }


@dataclass(frozen=True)
class ProvenanceEdge:
    source: str
    target: str
    kind: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "attributes": safe_value(self.attributes),
        }


class ProvenanceGraph:
    """A deterministic graph of observable data lineage within one run."""

    def __init__(self, *, run_id: str) -> None:
        self.run_id = run_id
        self.nodes: dict[str, ProvenanceNode] = {}
        self.edges: list[ProvenanceEdge] = []
        self.run_node = self.add_node("run", run_id, attributes={"run_id": run_id})

    @staticmethod
    def node_id(kind: str, label: str, digest: str | None = None) -> str:
        identity = {"label": label, "digest": digest}
        return f"{kind}:{fingerprint(identity)[:20]}"

    def add_node(
        self,
        kind: str,
        label: str,
        *,
        digest: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        node_id = self.node_id(kind, label, digest)
        if node_id not in self.nodes:
            self.nodes[node_id] = ProvenanceNode(
                node_id=node_id,
                kind=kind,
                label=label,
                digest=digest,
                attributes=dict(attributes or {}),
            )
        return node_id

    def add_edge(self, source: str, target: str, kind: str, *, attributes: dict[str, Any] | None = None) -> None:
        edge = ProvenanceEdge(source=source, target=target, kind=kind, attributes=dict(attributes or {}))
        if edge not in self.edges:
            self.edges.append(edge)

    def link_to_run(self, node_id: str, kind: str, *, attributes: dict[str, Any] | None = None) -> None:
        self.add_edge(node_id, self.run_node, kind, attributes=attributes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "run_id": self.run_id,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ProvenanceGraph:
        graph = cls(run_id=str(payload.get("run_id", "unknown")))
        graph.nodes.clear()
        for record in payload.get("nodes", []):
            node_id = str(record.get("id", ""))
            if node_id:
                graph.nodes[node_id] = ProvenanceNode(
                    node_id=node_id,
                    kind=str(record.get("kind", "unknown")),
                    label=str(record.get("label", "node")),
                    digest=record.get("digest"),
                    attributes=dict(record.get("attributes", {})),
                )
        graph.edges = [
            ProvenanceEdge(
                source=str(record.get("source", "")),
                target=str(record.get("target", "")),
                kind=str(record.get("kind", "related")),
                attributes=dict(record.get("attributes", {})),
            )
            for record in payload.get("edges", [])
            if record.get("source") and record.get("target")
        ]
        graph.run_node = next((node_id for node_id, node in graph.nodes.items() if node.kind == "run"), graph.run_node)
        return graph

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> ProvenanceGraph:
        run = manifest.get("run", {})
        graph = cls(run_id=str(run.get("run_id", "unknown")))
        graph.nodes[graph.run_node].attributes.update({"name": run.get("name"), "status": run.get("status")})

        for record in manifest.get("inputs", []):
            label = str(record.get("name", record.get("path", "input")))
            node = graph.add_node("input", label, digest=record.get("sha256"), attributes=record)
            graph.link_to_run(node, "input")
        for record in manifest.get("steps", []):
            label = str(record.get("name", "step"))
            node = graph.add_node("step", label, digest=(record.get("function") or {}).get("source_sha256"), attributes=record)
            graph.add_edge(graph.run_node, node, "contains")
            output = record.get("output") or {}
            if output.get("fingerprint"):
                value_node = graph.add_node("value", f"{label}:output", digest=output["fingerprint"], attributes=output)
                graph.add_edge(node, value_node, "produces")
        for record in manifest.get("outputs", []):
            label = str(record.get("name", record.get("path", "output")))
            node = graph.add_node("output", label, digest=record.get("sha256"), attributes=record)
            graph.link_to_run(node, "output")
        for record in manifest.get("observations", []):
            label = str(record.get("name", "observation"))
            summary = record.get("summary") or {}
            node = graph.add_node("observation", label, digest=summary.get("fingerprint"), attributes=record)
            graph.link_to_run(node, "observes")
        for record in manifest.get("checks", []):
            label = str(record.get("name", "check"))
            node = graph.add_node("check", label, digest=fingerprint(record), attributes=record)
            graph.add_edge(graph.run_node, node, "asserts")
        for index, record in enumerate(manifest.get("boundaries", [])):
            label = str(record.get("target") or record.get("kind") or f"boundary-{index}")
            node = graph.add_node("boundary", label, digest=fingerprint(record), attributes=record)
            graph.link_to_run(node, "limits")
        return graph


__all__ = ["ProvenanceEdge", "ProvenanceGraph", "ProvenanceNode"]
