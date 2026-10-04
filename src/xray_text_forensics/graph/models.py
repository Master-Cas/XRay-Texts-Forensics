"""Evidence graph models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source_id: str
    relation: str
    target_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def trace_to_artifact(self, evidence_id: str) -> list[str]:
        """Return one reverse path from evidence to an artifact, if present."""

        node_types = {node.node_id: node.node_type for node in self.nodes}
        reverse: dict[str, list[str]] = {}
        for edge in self.edges:
            reverse.setdefault(edge.target_id, []).append(edge.source_id)

        queue: list[tuple[str, list[str]]] = [(evidence_id, [evidence_id])]
        seen: set[str] = set()
        while queue:
            current, path = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if node_types.get(current) == "artifact":
                return path
            for parent in reverse.get(current, []):
                queue.append((parent, path + [parent]))
        return []
