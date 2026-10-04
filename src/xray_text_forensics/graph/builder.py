"""Build an evidence graph from a persistent case bundle."""

from __future__ import annotations

from xray_text_forensics.cases import CaseBundle

from .models import EvidenceGraph, GraphEdge, GraphNode


def build_evidence_graph(bundle: CaseBundle) -> EvidenceGraph:
    nodes: list[GraphNode] = [
        GraphNode(
            node_id=bundle.case.case_id,
            node_type="case",
            label=bundle.case.title,
        )
    ]
    edges: list[GraphEdge] = []

    for artifact in bundle.artifacts:
        nodes.append(
            GraphNode(
                node_id=artifact.artifact_id,
                node_type="artifact",
                label=artifact.original_filename or artifact.artifact_id,
                metadata={
                    "sha256": artifact.sha256,
                    "media_type": artifact.media_type,
                },
            )
        )
        edges.append(
            GraphEdge(
                source_id=bundle.case.case_id,
                relation="CONTAINS",
                target_id=artifact.artifact_id,
            )
        )

    for view in bundle.views:
        nodes.append(
            GraphNode(
                node_id=view.view_id,
                node_type="view",
                label=view.kind.value,
                metadata={"sha256": view.content_sha256},
            )
        )
        edges.append(
            GraphEdge(
                source_id=view.artifact_id,
                relation="DERIVED_AS",
                target_id=view.view_id,
            )
        )

    for run in bundle.runs:
        nodes.append(
            GraphNode(
                node_id=run.run_id,
                node_type="detector_run",
                label=f"{run.detector_id}@{run.detector_version}",
            )
        )
        edges.append(
            GraphEdge(
                source_id=run.artifact_id,
                relation="ANALYZED_BY",
                target_id=run.run_id,
            )
        )

    run_for_evidence: dict[str, str] = {}
    for run in bundle.runs:
        for evidence_id in run.evidence_ids:
            run_for_evidence[evidence_id] = run.run_id

    for item in bundle.evidence:
        nodes.append(
            GraphNode(
                node_id=item.evidence_id,
                node_type="evidence",
                label=item.finding or item.evidence_id,
                metadata={
                    "family": item.family.value,
                    "status": item.status.value,
                    "detector_id": item.detector_id,
                    "detector_version": item.detector_version,
                },
            )
        )
        if item.evidence_id in run_for_evidence:
            edges.append(
                GraphEdge(
                    source_id=run_for_evidence[item.evidence_id],
                    relation="PRODUCED",
                    target_id=item.evidence_id,
                )
            )
        elif item.derived_view_id is not None:
            edges.append(
                GraphEdge(
                    source_id=item.derived_view_id,
                    relation="OBSERVED",
                    target_id=item.evidence_id,
                )
            )
        else:
            edges.append(
                GraphEdge(
                    source_id=item.artifact_id,
                    relation="SUPPORTS",
                    target_id=item.evidence_id,
                )
            )

    for relationship in bundle.relationships:
        edges.append(
            GraphEdge(
                source_id=relationship.subject_id,
                relation=relationship.predicate,
                target_id=relationship.object_id,
                metadata=relationship.metadata,
            )
        )

    return EvidenceGraph(nodes=nodes, edges=edges)
