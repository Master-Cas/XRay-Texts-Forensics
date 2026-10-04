"""Command-line interface for XRay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from xray_text_forensics.detectors.unicode import UnicodeForensicsSuite
from xray_text_forensics.ingest import ForensicIngestor, IngestPolicy
from xray_text_forensics.runtime import analysis_context_from_ingest
from xray_text_forensics.storage import ContentAddressedStore

app = typer.Typer(
    name="xray",
    help="Evidence-driven text forensics.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """XRay command group."""


def _ingestor(store: Path, max_mib: int) -> ForensicIngestor:
    return ForensicIngestor(
        ContentAddressedStore(store),
        IngestPolicy(max_input_bytes=max_mib * 1024 * 1024),
    )


@app.command()
def ingest(
    path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    store: Annotated[
        Path,
        typer.Option("--store", help="Local content-addressed evidence store."),
    ] = Path(".xray-store"),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    max_mib: Annotated[
        int,
        typer.Option(min=1, help="Maximum input size in MiB."),
    ] = 100,
) -> None:
    """Preserve an artifact and create safe text views when supported."""

    result = _ingestor(store, max_mib).ingest_path(path)

    if json_output:
        typer.echo(result.model_dump_json(indent=2))
        return

    artifact = result.artifact
    typer.echo("XRAY FORENSIC INGEST")
    typer.echo(f"artifact_id: {artifact.artifact_id}")
    typer.echo(f"sha256:      {artifact.sha256}")
    typer.echo(f"bytes:       {artifact.byte_length}")
    typer.echo(f"media_type:  {artifact.media_type}")
    typer.echo(f"encoding:    {artifact.detected_encoding or 'n/a'}")
    typer.echo(f"views:       {len(result.views)}")
    typer.echo(f"warnings:    {len(result.warnings)}")


@app.command("unicode")
def unicode_scan(
    path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    store: Annotated[
        Path,
        typer.Option("--store", help="Local content-addressed evidence store."),
    ] = Path(".xray-store"),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    max_mib: Annotated[
        int,
        typer.Option(min=1, help="Maximum input size in MiB."),
    ] = 100,
) -> None:
    """Run deterministic Unicode forensics over the best preserved text view."""

    ingest_result = _ingestor(store, max_mib).ingest_path(path)
    context = analysis_context_from_ingest(ingest_result)
    evidence = UnicodeForensicsSuite().analyze(context)

    if json_output:
        payload = {
            "artifact": ingest_result.artifact.model_dump(mode="json"),
            "views": [view.model_dump(mode="json") for view in ingest_result.views],
            "warnings": [warning.model_dump(mode="json") for warning in ingest_result.warnings],
            "evidence": [item.model_dump(mode="json") for item in evidence],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo("XRAY UNICODE FORENSICS")
    typer.echo(f"artifact: {ingest_result.artifact.artifact_id}")
    for item in evidence:
        count = item.parameters.get("total_count", item.parameters.get("total_sequences", ""))
        suffix = f" ({count})" if count != "" else ""
        typer.echo(f"{item.finding}: {item.status}{suffix}")
