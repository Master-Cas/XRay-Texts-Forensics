import json

import pytest
from typer.testing import CliRunner

from xray_text_forensics.blackbox import (
    BlackBoxDesign,
    BlackBoxExperiment,
    RecordedProviderIdentity,
    SyntheticChoiceProvider,
    load_design,
    load_observations_jsonl,
    save_design,
    save_observations_jsonl,
)
from xray_text_forensics.cli import app

runner = CliRunner()


def design() -> BlackBoxDesign:
    return BlackBoxDesign(
        prefixes=["Prefix A", "Prefix B", "Prefix C"],
        contexts=["731902846215703", "846215703928164", "294681503728190", "503728194650281"],
        candidates=["amber", "berry", "cedar"],
        samples_per_cell=12,
        permutation_count=99,
        alpha=0.05,
        seed=77,
    )


def test_design_and_observations_roundtrip(tmp_path) -> None:
    frozen = design()
    experiment = BlackBoxExperiment(frozen)
    provider = SyntheticChoiceProvider(watermark_on=True, seed=frozen.seed)
    observations = experiment.collect(provider)

    design_path = tmp_path / "design.json"
    rows_path = tmp_path / "observations.jsonl"
    save_design(design_path, frozen)
    save_observations_jsonl(rows_path, observations)

    loaded_design = load_design(design_path)
    loaded_rows = load_observations_jsonl(rows_path)
    assert loaded_design == frozen
    assert loaded_rows == observations
    assert all(row.design_sha256 == frozen.fingerprint() for row in loaded_rows)


def test_observation_fingerprint_mismatch_fails_closed() -> None:
    frozen = design()
    experiment = BlackBoxExperiment(frozen)
    rows = experiment.collect(
        SyntheticChoiceProvider(watermark_on=False, seed=frozen.seed)
    )
    changed = frozen.model_copy(update={"seed": frozen.seed + 1})
    with pytest.raises(ValueError, match="fingerprint"):
        BlackBoxExperiment(changed).analyze(
            RecordedProviderIdentity("recorded", "model"),
            rows,
        )


def test_synthetic_on_off_share_identical_random_draws() -> None:
    off = SyntheticChoiceProvider(watermark_on=False, seed=123)
    on = SyntheticChoiceProvider(watermark_on=True, seed=123)
    assert off._draw("prefix", "context", 7) == on._draw("prefix", "context", 7)


def test_blackbox_analyze_cli_uses_recorded_identity(tmp_path) -> None:
    frozen = design()
    experiment = BlackBoxExperiment(frozen)
    rows = experiment.collect(
        SyntheticChoiceProvider(watermark_on=True, seed=frozen.seed)
    )
    design_path = tmp_path / "design.json"
    rows_path = tmp_path / "observations.jsonl"
    save_design(design_path, frozen)
    save_observations_jsonl(rows_path, rows)

    result = runner.invoke(
        app,
        [
            "blackbox-analyze",
            str(design_path),
            str(rows_path),
            "--provider-id",
            "external.provider",
            "--model-id",
            "external-model-v1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["provider_id"] == "external.provider"
    assert payload["model_id"] == "external-model-v1"
    assert payload["design_sha256"] == frozen.fingerprint()
    assert payload["observation_count"] == len(rows)
