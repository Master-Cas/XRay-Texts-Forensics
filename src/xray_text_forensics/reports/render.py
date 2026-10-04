"""JSON, HTML, and PDF forensic case reports."""

from __future__ import annotations

import html
import json
import textwrap
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from xray_text_forensics.cases import CaseBundle
from xray_text_forensics.graph import EvidenceGraph


def render_json_report(bundle: CaseBundle, graph: EvidenceGraph) -> str:
    payload = {
        "case": bundle.model_dump(mode="json"),
        "evidence_graph": graph.model_dump(mode="json"),
        "scientific_note": (
            "Evidence families are reported separately. This report does not create a "
            "universal AI score or infer authorship from stylistic similarity alone."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_html_report(bundle: CaseBundle, graph: EvidenceGraph) -> str:
    evidence_rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(item.evidence_id)}</code></td>"
        f"<td>{html.escape(item.family.value)}</td>"
        f"<td>{html.escape(item.status.value)}</td>"
        f"<td>{html.escape(item.finding or '')}</td>"
        f"<td><code>{html.escape(item.detector_id)}@"
        f"{html.escape(item.detector_version)}</code></td>"
        f"<td>{html.escape(item.reason or '')}</td>"
        "</tr>"
        for item in bundle.evidence
    )
    artifact_rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(item.artifact_id)}</code></td>"
        f"<td>{html.escape(item.original_filename or '')}</td>"
        f"<td><code>{html.escape(item.sha256)}</code></td>"
        f"<td>{html.escape(item.media_type)}</td>"
        "</tr>"
        for item in bundle.artifacts
    )
    trace_rows = "".join(
        "<li><code>"
        + html.escape(item.evidence_id)
        + "</code> → "
        + html.escape(" ← ".join(graph.trace_to_artifact(item.evidence_id)))
        + "</li>"
        for item in bundle.evidence
    )

    verified = "VERIFIED" if bundle.audit_verified else "INVALID"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>XRay Forensic Report — {html.escape(bundle.case.title)}</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; line-height: 1.45; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
th, td {{ border: 1px solid #999; padding: .45rem; vertical-align: top; }}
code {{ overflow-wrap: anywhere; }}
.notice {{ border: 1px solid #777; padding: 1rem; }}
</style>
</head>
<body>
<h1>XRay Forensic Report</h1>
<p><strong>Case:</strong> {html.escape(bundle.case.title)}
(<code>{html.escape(bundle.case.case_id)}</code>)</p>
<p><strong>Audit chain:</strong> {verified}</p>
<div class="notice">
<strong>Scientific interpretation:</strong>
Evidence families remain separate. No universal AI score is calculated.
Stylometric similarity is not authorship proof, and absence of detectable evidence
is not proof that a signal never existed.
</div>
<h2>Artifacts</h2>
<table>
<thead><tr><th>ID</th><th>Filename</th><th>SHA-256</th><th>Media type</th></tr></thead>
<tbody>{artifact_rows}</tbody>
</table>
<h2>Evidence</h2>
<table>
<thead><tr><th>Evidence ID</th><th>Family</th><th>Status</th><th>Finding</th>
<th>Detector</th><th>Reason</th></tr></thead>
<tbody>{evidence_rows}</tbody>
</table>
<h2>Traceability</h2>
<ul>{trace_rows}</ul>
<p>Graph nodes: {len(graph.nodes)} — Graph edges: {len(graph.edges)}</p>
</body>
</html>
"""


def render_pdf_report(bundle: CaseBundle, graph: EvidenceGraph) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    _, height = A4
    y = height - 50

    def line(text: str, *, indent: int = 0) -> None:
        nonlocal y
        for wrapped in textwrap.wrap(text, width=max(30, 100 - indent)):
            if y < 50:
                canvas.showPage()
                y = height - 50
            canvas.drawString(50 + indent * 8, y, wrapped)
            y -= 14

    canvas.setTitle(f"XRay Forensic Report - {bundle.case.title}")
    canvas.setFont("Helvetica-Bold", 14)
    line("XRay Forensic Report")
    canvas.setFont("Helvetica", 9)
    line(f"Case: {bundle.case.title} ({bundle.case.case_id})")
    line(f"Audit chain: {'VERIFIED' if bundle.audit_verified else 'INVALID'}")
    line(
        "Scientific note: Evidence families remain separate. No universal AI score is "
        "calculated. Stylometric similarity is not authorship proof."
    )
    line("Artifacts:")
    for artifact in bundle.artifacts:
        line(
            f"{artifact.artifact_id} | {artifact.original_filename or ''} | "
            f"SHA-256 {artifact.sha256}",
            indent=1,
        )
    line("Evidence:")
    for item in bundle.evidence:
        line(
            f"{item.evidence_id} | {item.family.value} | {item.status.value} | "
            f"{item.finding or ''} | {item.detector_id}@{item.detector_version}",
            indent=1,
        )
        trace = graph.trace_to_artifact(item.evidence_id)
        if trace:
            line("Trace: " + " <- ".join(trace), indent=2)

    canvas.save()
    return buffer.getvalue()
