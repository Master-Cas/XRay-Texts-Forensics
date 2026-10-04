"""Command-line interface for XRay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from xray_text_forensics.calibration import CalibrationConfig, calibrate, evaluate
from xray_text_forensics.calibration.io import load_score_jsonl
from xray_text_forensics.corpus import CorpusEngine
from xray_text_forensics.corpus.loaders import load_directory
from xray_text_forensics.detectors.unicode import UnicodeForensicsSuite
from xray_text_forensics.detectors.watermark import (
    EnvironmentSecretProvider,
    RedGreenConfig,
    ReferenceRedGreenDetector,
    StableWordTokenizer,
)
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
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    store: Annotated[
        Path,
        typer.Option("--store", help="Local content-addressed evidence store."),
    ] = Path(".xray-store"),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    max_mib: Annotated[int, typer.Option(min=1, help="Maximum input size in MiB.")] = 100,
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
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    store: Annotated[
        Path,
        typer.Option("--store", help="Local content-addressed evidence store."),
    ] = Path(".xray-store"),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    max_mib: Annotated[int, typer.Option(min=1, help="Maximum input size in MiB.")] = 100,
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


@app.command("compare-corpora")
def compare_corpora(
    corpus_a: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    corpus_b: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    store: Annotated[
        Path,
        typer.Option("--store", help="Local content-addressed evidence store."),
    ] = Path(".xray-store"),
    context_kind: Annotated[
        str,
        typer.Option("--context", help="Co-occurrence context: sentence or paragraph."),
    ] = "sentence",
    top_n: Annotated[int, typer.Option("--top", min=1, help="Specificity rows.")] = 30,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compare two directories as linguistic corpora."""

    ingestor = _ingestor(store, 100)
    documents_a, warnings_a = load_directory(corpus_a, ingestor)
    documents_b, warnings_b = load_directory(corpus_b, ingestor)
    engine_a = CorpusEngine(documents_a, name=corpus_a.name, context_kind=context_kind)
    engine_b = CorpusEngine(documents_b, name=corpus_b.name, context_kind=context_kind)
    comparison = engine_a.compare(engine_b, top_n=top_n)

    if json_output:
        payload = comparison.model_dump(mode="json")
        payload["warnings"] = {"a": warnings_a, "b": warnings_b}
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo("XRAY CORPUS COMPARISON")
    typer.echo(f"A: {comparison.corpus_a.name} ({comparison.corpus_a.document_count} docs)")
    typer.echo(f"B: {comparison.corpus_b.name} ({comparison.corpus_b.document_count} docs)")
    typer.echo(f"TF-IDF cosine:       {comparison.cosine_similarity:.4f}")
    typer.echo(f"Intertextual distance: {comparison.intertextual_distance:.4f}")
    typer.echo("Top specificity:")
    for row in comparison.specificity[:10]:
        typer.echo(
            f"  {row.term:<24} chi2={row.chi_square:8.3f} "
            f"log2FC={row.log2_fold_change_a_over_b:+7.3f} -> {row.direction}"
        )


@app.command("watermark-redgreen")
def watermark_redgreen(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    key_env: Annotated[
        str,
        typer.Option("--key-env", help="Environment variable containing the secret key."),
    ],
    store: Annotated[
        Path,
        typer.Option("--store", help="Local content-addressed evidence store."),
    ] = Path(".xray-store"),
    threshold_z: Annotated[
        float,
        typer.Option("--threshold-z", help="Detection z-score threshold."),
    ] = 4.0,
    min_tokens: Annotated[
        int,
        typer.Option("--min-tokens", min=1, help="Minimum scored tokens."),
    ] = 50,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Score the reference known-key red/green watermark detector."""

    ingest_result = _ingestor(store, 100).ingest_path(path)
    context = analysis_context_from_ingest(ingest_result)
    context.resources.update(
        {
            "secret_provider": EnvironmentSecretProvider(),
            "secret_ref": key_env,
            "watermark_tokenizer": StableWordTokenizer(),
        }
    )
    detector = ReferenceRedGreenDetector(
        RedGreenConfig(threshold_z=threshold_z, min_scored_tokens=min_tokens)
    )
    evidence = detector.analyze(context)

    if json_output:
        typer.echo(
            json.dumps(
                {"evidence": [item.model_dump(mode="json") for item in evidence]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    item = evidence[0]
    typer.echo("XRAY KNOWN-KEY WATERMARK")
    typer.echo(f"status: {item.status}")
    typer.echo(f"finding: {item.finding}")
    if "z_score" in item.parameters:
        typer.echo(f"z_score: {item.parameters['z_score']:.4f}")
    if item.reason:
        typer.echo(f"reason: {item.reason}")


@app.command("calibrate-scores")
def calibrate_scores(
    development_controls: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    held_out_test: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    detector_id: Annotated[str, typer.Option("--detector-id")],
    detector_version: Annotated[str, typer.Option("--detector-version")] = "unknown",
    dataset_id: Annotated[str, typer.Option("--dataset-id")] = "dataset",
    dataset_version: Annotated[str, typer.Option("--dataset-version")] = "unknown",
    target_fpr: Annotated[
        float,
        typer.Option("--target-fpr", min=0.0, max=1.0),
    ] = 0.01,
    lower_is_positive: Annotated[
        bool,
        typer.Option("--lower-is-positive", help="Lower scores indicate positives."),
    ] = False,
    min_controls: Annotated[
        int,
        typer.Option("--min-controls", min=1),
    ] = 100,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Calibrate on development controls and evaluate once on held-out scores."""

    controls = load_score_jsonl(development_controls)
    test_samples = load_score_jsonl(held_out_test)
    config = CalibrationConfig(
        target_fpr=target_fpr,
        higher_is_positive=not lower_is_positive,
        min_control_samples=min_controls,
    )
    manifest = calibrate(
        controls,
        config=config,
        detector_id=detector_id,
        detector_version=detector_version,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
    )
    report = evaluate(test_samples, manifest)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return

    typer.echo("XRAY CALIBRATION / HELD-OUT EVALUATION")
    typer.echo(f"threshold: {manifest.threshold:.8g}")
    typer.echo(f"dev empirical FPR: {manifest.dev_empirical_fpr:.6f}")
    typer.echo(f"held-out FPR: {report.fpr:.6f}")
    typer.echo(f"held-out TPR: {report.tpr:.6f}")
    typer.echo(f"ROC-AUC: {report.roc_auc if report.roc_auc is not None else 'n/a'}")
