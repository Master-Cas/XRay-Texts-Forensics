"""Command-line interface for XRay."""

from __future__ import annotations

from pathlib import Path

import typer

from xray_text_forensics.ingest import ForensicIngestor, IngestPolicy
from xray_text_forensics.storage import ContentAddressedStore

app = typer.Typer(
    name="xray",
    help="Evidence-driven text forensics.",
    no_args_is_help=True,
)


@app.command()
def ingest(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    store: Path = typer.Option(
        Path(".xray-store"),
        "--store",
        help="Local content-addressed evidence store.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    max_mib: int = typer.Option(100, min=1, help="Maximum input size in MiB."),
) -> None:
    """Preserve an artifact and create safe M1 text views when supported."""

    ingestor = ForensicIngestor(
        ContentAddressedStore(store),
        IngestPolicy(max_input_bytes=max_mib * 1024 * 1024),
    )
    result = ingestor.ingest_path(path)

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
